#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from absolute_completion_common import completion_path, now_iso, write_json, write_text


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
AUDIT_JSON_NAME = "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json"
AUDIT_MARKDOWN_NAME = "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.md"
CONTRACT_NAME = "chummer.mobile_pwa_public_projection.v2"
RETIRED_ENV_KEYS = {
    "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED",
    "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED",
    "CHUMMER_PUBLIC_PLAY_PROXY_URL",
    "CHUMMER_PUBLIC_PLAY_PROXY_API_KEY",
}
EXPECTED_BUILD_FINAL_ROUTE = "/app?command=character_roster"
EXPECTED_HOME_OPEN_CHUMMER_MARKERS = {
    "Open Chummer",
    'site-open-chummer-menu',
    'aria-label="Open Chummer options"',
    'data-analytics-label="Build">Build</button>',
    'href="/mobile/player"',
    'data-analytics-label="Play">Play</a>',
}
EXPECTED_BUILD_SHELL_MARKERS = {
    "Character Roster",
    "Chummer Online",
}
EXPECTED_BUILD_SHELL_VARIANT_MARKERS = {
    "browser-app-roster",
    "browser-preview-shell",
}
EXPECTED_PLAY_SHELL_MARKERS = {
    "pwa-ledger-stream",
    "data-pwa-install-state",
    "data-pwa-ledger-status",
    "data-pwa-ledger-heat-meter",
}
EXPECTED_SHORTCUTS = {"/mobile", "/play", "/play/continuity"}
EXPECTED_SHELL_CACHE_PATHS = {"/mobile", "/play", "/play/continuity", "/mobile/pwa.json", "/ready/handoff/mobile.json"}
EXPECTED_PWA_LEDGER_STATUSES = {"opt_in_required", "no_world_data", "live", "world_not_followed"}
EXPECTED_NOTIFICATION_ROUTE_PATHS = {"/account/ledger/notifications", "/mobile", "/play", "/play/continuity", "/ledger/map", "/passport"}
EXPECTED_NOTIFICATION_ROUTE_PREFIXES = {"/account/ledger/factions/", "/ledger/turns/", "/ledger/newsroom/", "/passport/receipts/"}
EXPECTED_NOTIFICATION_ASSET_PATHS = {"/apple-touch-icon.png", "/favicon.ico", "/favicon.svg", "/pwa-icon.svg"}
EXPECTED_NOTIFICATION_ASSET_SUFFIXES = {".ico", ".png", ".svg", ".webp"}
PERSONALIZED_LEDGER_STREAM_ROUTE = "/mobile/pwa/ledger.json"
SERVICE_WORKER_REGISTRATION_RE = re.compile(r'serviceWorker\.register\("([^"]*service-worker\.js[^"]*)"')


def load_static_verifier():
    path = RUN_SERVICES_ROOT / "scripts" / "verify_public_pwa_static_assets.py"
    spec = importlib.util.spec_from_file_location("verify_public_pwa_static_assets_for_projection", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_audit_artifacts(payload: dict[str, Any], markdown: str) -> None:
    destinations = {
        completion_path(AUDIT_JSON_NAME),
        PUBLISHED_ROOT / AUDIT_JSON_NAME,
    }
    for path in destinations:
        write_json(path, payload)
    for path in {
        completion_path(AUDIT_MARKDOWN_NAME),
        PUBLISHED_ROOT / AUDIT_MARKDOWN_NAME,
    }:
        write_text(path, markdown)


def compose_topology(source_root: Path, failures: list[str]) -> dict[str, Any]:
    text = (source_root / "docker-compose.public-edge.yml").read_text(encoding="utf-8")
    profile_only = 'profiles: ["play-private"]' in text
    default_off = 'CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "${CHUMMER_PUBLIC_PLAY_PROXY_ENABLED:-false}"' in text
    no_edge_secret = "CHUMMER_PUBLIC_PLAY_PROXY_API_KEY" not in text
    no_edge_upstream = "CHUMMER_PUBLIC_PLAY_PROXY_URL:" not in text
    portal_dependencies = text.split("  chummer-portal:", 1)[1].split("    environment:", 1)[0]
    no_default_dependency = "chummer-play-web:" not in portal_dependencies
    checks = {
        "privatePlayProfileOnly": profile_only,
        "publicProjectionDefaultOff": default_off,
        "edgeServiceKeyAbsent": no_edge_secret,
        "edgeUpstreamAbsent": no_edge_upstream,
        "portalHasNoPlayDependency": no_default_dependency,
    }
    for name, passed in checks.items():
        if not passed:
            failures.append(f"compose topology failed: {name}")
    return checks


def source_topology(source_root: Path = RUN_SERVICES_ROOT) -> dict[str, Any]:
    failures: list[str] = []
    static_verifier = load_static_verifier()
    static_assets = static_verifier.verify_source(source_root)
    if static_assets["status"] != "pass":
        failures.extend(f"static assets: {failure}" for failure in static_assets["failures"])

    api = source_root / "Chummer.Run.Api"
    gateway = (api / "Services" / "PublicPlayProxyGateway.cs").read_text(encoding="utf-8")
    program = (api / "Program.cs").read_text(encoding="utf-8")
    controller = (api / "Controllers" / "PublicLandingController.cs").read_text(encoding="utf-8")
    model = (api / "ViewModels" / "SiteViewModels.cs").read_text(encoding="utf-8")
    view = (api / "Views" / "PublicLanding" / "MobileProjection.cshtml").read_text(encoding="utf-8")
    env_example = (source_root / ".env.example").read_text(encoding="utf-8")
    play_action = controller.split("public IActionResult PlayProjectionPage()", 1)[1].split(
        '[HttpGet("/player")]', 1
    )[0]

    gateway_checks = {
        "zeroPublicPaths": "Array.Empty<string>()" in gateway,
        "alwaysNotMatched": "Task.FromResult(PublicPlayProxyDisposition.NotMatched)" in gateway,
        "noHttpClient": "IHttpClientFactory" not in gateway and "HttpRequestMessage" not in gateway,
        "notInRequestPipeline": "playProjectionGateway.TryHandleAsync" not in program and "gateway.TryHandleAsync" not in program,
    }
    readiness_checks = {
        "combinedReadyField": "HubReadyResponse combinedReport = HubReadyResponse.Create(" in program
        and "report,\n        projection,\n        deploymentIdentity);" in program,
        "combinedBodyReturned": "Results.Json(\n        combinedReport" in program,
        "projectionReadinessRoute": '"/api/ready/play-projection"' in program,
    }
    role_checks = {
        "playAppliesPrivateHeaders": "ApplyPrivateMobileDocumentHeaders();" in play_action,
        "playCanonicalRedirect": "ResolveCanonicalPlayRoleFromQuery(Request.Query)" in play_action
        and 'return Redirect($"/mobile/{canonicalRole}");' in play_action,
        "closedRoleAliases": all(alias in controller for alias in ('"game-master"', '"runner"', '"spectator"')),
        "roleFieldsInModel": all(field in model for field in ("InstallRoleKey", "DocumentTitle", "ManifestHref", "AppleAppTitle", "MobileInstallRoleProfileViewModel")),
        "viewUsesModelManifest": 'ViewData["MobileManifestHref"] = Model.ManifestHref;' in view,
        "viewUsesModelRole": 'data-install-role="@roleProfile.RoleKey"' in view,
        "roleSpecificBody": all(f"roleProfile.{field}" in view for field in ("PurposeHeading", "PrivacyHeading", "AuthorityHeading", "InstallTargetPath", "Capabilities")),
        "roleSpecificQr": "data-mobile-app-inline-handoff" in view and "data-mobile-app-inline-qr" in view,
        "installOnly": 'data-play-surface="install-only"' in view and "mobile-turn-companion.js" not in view,
        "networkClosedCsp": "connect-src 'none'" in controller,
    }
    env_checks = {key: f"{key}=" not in env_example for key in RETIRED_ENV_KEYS}

    for group, checks in (
        ("gateway", gateway_checks),
        ("readiness", readiness_checks),
        ("role shell", role_checks),
        ("env example", env_checks),
    ):
        for name, passed in checks.items():
            if not passed:
                failures.append(f"{group} failed: {name}")

    topology = compose_topology(source_root, failures)
    return {
        "contractName": CONTRACT_NAME,
        "mode": "source",
        "generatedAt": now_iso(),
        "status": "pass" if not failures else "fail",
        "topology": topology,
        "gateway": gateway_checks,
        "readiness": readiness_checks,
        "roleShell": role_checks,
        "retiredEnvAbsent": env_checks,
        "staticAssets": static_assets,
        "failures": failures,
    }


def live_projection(base_url: str, session: requests.Session | None = None) -> dict[str, Any]:
    failures: list[str] = []
    client = session or requests.Session()
    static_verifier = load_static_verifier()
    static_assets = static_verifier.verify_live(base_url, 30.0)
    if static_assets["status"] != "pass":
        failures.extend(f"static assets: {failure}" for failure in static_assets["failures"])

    ready_response = client.get(f"{base_url.rstrip('/')}/api/ready", timeout=30)
    try:
        ready_payload = ready_response.json()
    except ValueError:
        ready_payload = {}
    hub_value = ready_payload.get("hub")
    hub = hub_value if isinstance(hub_value, dict) else {}
    projection_value = ready_payload.get("playProjection")
    projection = projection_value if isinstance(projection_value, dict) else {}
    deployment_identity_value = ready_payload.get("deploymentIdentity")
    deployment_identity = (
        deployment_identity_value if isinstance(deployment_identity_value, dict) else {}
    )
    deployment_fingerprint = str(
        deployment_identity.get("sourceFingerprintSha256") or ""
    ).strip().lower()
    readiness_checks = {
        "http200": ready_response.status_code == 200,
        "bodyReady": ready_payload.get("ready") is True,
        "bodyStatus": str(ready_payload.get("status") or "").strip().lower() == "ready",
        "hubObject": isinstance(hub_value, dict),
        "hubReady": hub.get("ready") is True,
        "hubStatus": str(hub.get("status") or "").strip().lower() == "pass",
        "projectionObject": isinstance(projection_value, dict),
        "projectionDisabled": projection.get("enabled") is False,
        "projectionReady": projection.get("ready") is True,
        "projectionStatus": str(projection.get("status") or "").strip().lower() == "disabled",
        "deploymentIdentityObject": isinstance(deployment_identity_value, dict),
        "deploymentIdentityReady": deployment_identity.get("ready") is True,
        "deploymentIdentityCode": str(deployment_identity.get("code") or "").strip().lower()
        == "overlay_identity_bound",
        "deploymentIdentityFingerprint": len(deployment_fingerprint) == 64
        and all(character in "0123456789abcdef" for character in deployment_fingerprint),
    }
    readiness_checks["combinedConsistent"] = all(readiness_checks.values())
    for name, passed in readiness_checks.items():
        if not passed:
            failures.append(f"/api/ready: {name} failed")

    canonical_origin = urlsplit(base_url.rstrip("/"))
    role_results: dict[str, Any] = {}
    role_probe_results: dict[str, Any] = {}
    for probe_name, path, role in ROLE_PROBES:
        _, manifest, title, purpose, capability, target = ROLE_SHELLS[role]
        response = client.get(f"{base_url.rstrip('/')}{path}", timeout=30, allow_redirects=True)
        markup = response.text
        final_url = urlsplit(getattr(response, "url", ""))
        history = list(getattr(response, "history", []))
        redirect_locations = [str(item.headers.get("Location", "")) for item in history]
        resolved_redirects = [urlsplit(urljoin(f"{base_url.rstrip('/')}/", location)) for location in redirect_locations]
        clean_history_locations = bool(resolved_redirects) and all(
            redirect.path == target
            and not redirect.query
            and not redirect.fragment
            and redirect.scheme == canonical_origin.scheme
            and redirect.netloc == canonical_origin.netloc
            and not any(marker in location.lower() for marker in SENSITIVE_REDIRECT_MARKERS)
            for location, redirect in zip(redirect_locations, resolved_redirects, strict=True)
        )
        checks = {
            "status": response.status_code == 200,
            "exactlyOneRedirect": len(history) == 1,
            "temporaryRedirect": len(history) == 1 and history[0].status_code == 302,
            "cleanRedirectLocations": clean_history_locations,
            "cleanFinalUrl": final_url.scheme == canonical_origin.scheme
            and final_url.netloc == canonical_origin.netloc
            and final_url.path == target
            and not final_url.query
            and not final_url.fragment,
            "role": f'data-install-role="{role}"' in markup,
            "manifest": f'href="{manifest}"' in markup,
            "title": title in markup,
            "purpose": purpose in markup,
            "capability": capability in markup,
            "cleanOpenTarget": f'href="{target}"' in markup,
            "roleQr": "data-mobile-app-inline-qr" in markup
            and f'data-mobile-app-path="{target}"' in markup,
            "privacyBoundary": f'data-role-privacy-warning="{role}"' in markup,
            "authorityBoundary": f'data-role-authority-warning="{role}"' in markup,
            "installOnly": 'data-play-surface="install-only"' in markup,
            "noBlazor": "/_framework/blazor.web.js" not in markup,
            "noPrivateScript": "mobile-turn-companion.js" not in markup,
            "noStore": "no-store" in response.headers.get("Cache-Control", "").lower(),
            "closedCsp": "connect-src 'none'" in response.headers.get("Content-Security-Policy", ""),
        }
        role_probe_results[probe_name] = {
            "path": path,
            "expectedRole": role,
            "expectedTarget": target,
            "historyCount": len(history),
            "redirectLocations": redirect_locations,
            "checks": checks,
        }
        if probe_name in ROLE_SHELLS:
            role_results[probe_name] = checks
        for name, passed in checks.items():
            if not passed:
                failures.append(f"{probe_name} ({path}): {name} failed")

    return {
        "contractName": CONTRACT_NAME,
        "mode": "live",
        "baseUrl": base_url.rstrip("/"),
        "generatedAt": now_iso(),
        "status": "pass" if not failures else "fail",
        "readiness": {
            "httpStatus": ready_response.status_code,
            "payload": ready_payload,
            "checks": readiness_checks,
        },
        "roleShells": role_results,
        "roleProbes": role_probe_results,
        "staticAssets": static_assets,
        "failures": failures,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Mobile PWA public projection audit",
            "",
            f"- Status: `{payload['status']}`",
            f"- Mode: `{payload['mode']}`",
            "- Public edge posture: local install-only assets; remote projection retired.",
            "- Private Play posture: explicit Compose profile only.",
            f"- Failure count: `{len(payload['failures'])}`",
            "",
        ]
    )


def run(
    base_url: str = "",
    mobile_release_proof_path: Path | None = None,
    *,
    source_root: Path = RUN_SERVICES_ROOT,
    session: requests.Session | None = None,
) -> int:
    payload = live_projection(base_url, session=session) if base_url else source_topology(source_root)
    payload["legacyMobileReleaseProof"] = {
        "path": str(mobile_release_proof_path) if mobile_release_proof_path else "",
        "gating": False,
        "reason": "The public edge now verifies its local install-only contract directly.",
    }
    write_audit_artifacts(payload, render_markdown(payload))
    if payload["status"] == "pass":
        print("mobile_pwa_public_projection:ok")
        return 0
    for failure in payload["failures"]:
        print(f"mobile_pwa_public_projection:error:{failure}")
    return 1


def is_public_product_route(value: object) -> bool:
    route = str(value or "").strip()
    return (
        route.startswith("/")
        and ".json" not in route.lower()
        and not route.lower().startswith("/api/")
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the first-party mobile/PWA public projection.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    parser.add_argument("--completion-dir", default="", help="Optional directory for default JSON and Markdown receipts.")
    parser.add_argument("--output", default="", help="Optional JSON receipt path.")
    parser.add_argument("--report", default="", help="Optional Markdown report path.")
    return parser.parse_args()


def resolve_output_paths(completion_dir: str = "", output: str = "", report: str = "") -> tuple[Path, Path]:
    if output:
        output_path = Path(output)
    elif completion_dir:
        output_path = Path(completion_dir) / "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json"
    else:
        output_path = completion_path("MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json")

    if report:
        report_path = Path(report)
    elif completion_dir:
        report_path = Path(completion_dir) / "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.md"
    elif output:
        report_path = output_path.with_suffix(".md")
    else:
        report_path = completion_path("MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.md")

    return output_path, report_path


def run(base_url: str, *, output_path: Path | None = None, report_path: Path | None = None) -> int:
    session = requests.Session()
    route_results = []
    for route in ROUTES:
        response = session.get(f"{base_url}{route}", timeout=30, allow_redirects=True)
        response.raise_for_status()
        final_url = response.url
        parsed_final = urlparse(final_url)
        final_route = f"{parsed_final.path}{f'?{parsed_final.query}' if parsed_final.query else ''}"
        route_results.append(
            {
                "route": route,
                "status_code": response.status_code,
                "final_url": final_url,
                "final_route": final_route,
                "expected_final_route": EXPECTED_FINAL_ROUTES[route],
            }
        )

    mobile_html = session.get(f"{base_url}/mobile", timeout=30)
    mobile_html.raise_for_status()
    home_html = session.get(f"{base_url}/", timeout=30)
    home_html.raise_for_status()
    build_html = session.get(f"{base_url}/build", timeout=30, allow_redirects=True)
    build_html.raise_for_status()
    play_shell_html = session.get(f"{base_url}/play", timeout=30, allow_redirects=True)
    play_shell_html.raise_for_status()
    continuity_html = session.get(f"{base_url}/play/continuity", timeout=30)
    continuity_html.raise_for_status()
    mobile_json_response = session.get(f"{base_url}/mobile/pwa.json", timeout=30)
    mobile_json_response.raise_for_status()
    ledger_stream_response = session.get(f"{base_url}/mobile/pwa/ledger.json", timeout=30)
    ledger_stream_response.raise_for_status()
    continuity_receipt_paths = (
        "/play/continuity/history",
        "/play/continuity/receipts",
    )
    receipt_index_response = None
    receipt_index_route = None
    for candidate_path in continuity_receipt_paths:
        response = session.get(f"{base_url}{candidate_path}", timeout=30)
        if response.status_code == 200:
            receipt_index_response = response
            receipt_index_route = candidate_path
            break

    if receipt_index_response is None:
        raise RuntimeError(
            f"continuity receipt route not available on {base_url}; expected one of "
            f"{', '.join(continuity_receipt_paths)}"
        )
    receipt_index_response.raise_for_status()
    manifest_response = session.get(f"{base_url}/manifest.json", timeout=30)
    manifest_response.raise_for_status()
    registered_service_worker_path = extract_registered_service_worker_path(mobile_html.text)
    service_worker_path = registered_service_worker_path or "/service-worker.js"
    service_worker_response = session.get(urljoin(f"{base_url}/", service_worker_path.lstrip("/")), timeout=30)
    service_worker_response.raise_for_status()

    manifest = manifest_response.json()
    mobile_json = mobile_json_response.json()
    ledger_stream = ledger_stream_response.json()
    receipt_index = receipt_index_response.json()
    service_worker_text = service_worker_response.text
    precache_urls = extract_js_string_array(service_worker_text, "PRECACHE_URLS")
    non_cacheable_paths = extract_js_string_array(service_worker_text, "NON_CACHEABLE_PATHS")
    notification_route_paths = extract_js_string_array(service_worker_text, "NOTIFICATION_ROUTE_PATHS")
    notification_route_prefixes = extract_js_string_array(service_worker_text, "NOTIFICATION_ROUTE_PREFIXES")
    notification_asset_paths = extract_js_string_array(service_worker_text, "NOTIFICATION_ASSET_PATHS")
    notification_asset_suffixes = extract_js_string_array(service_worker_text, "NOTIFICATION_ASSET_SUFFIXES")
    ledger_stream_cache_control = ledger_stream_response.headers.get("Cache-Control", "")
    ledger_stream_vary = ledger_stream_response.headers.get("Vary", "")
    has_manifest_link = 'rel="manifest"' in mobile_html.text and (
        "/manifest.json" in mobile_html.text
        or ".webmanifest" in mobile_html.text
    )
    has_sw_registration = (
        registered_service_worker_path is not None
        or 'const CACHE_NAME = "chummer-public-v4";' in service_worker_text
    )
    has_install_button = (
        "Install this app" in mobile_html.text
        or (
            'rel="manifest"' in mobile_html.text
            and "apple-mobile-web-app-capable" in mobile_html.text
        )
    )
    has_continuity_action = "/play/continuity" in mobile_html.text or mobile_json.get("continuity_route") == "/play/continuity"
    home_open_chummer_missing_markers = sorted(
        marker for marker in EXPECTED_HOME_OPEN_CHUMMER_MARKERS if marker not in home_html.text
    )
    home_open_chummer_dropdown_holds = not home_open_chummer_missing_markers
    build_final_url = build_html.url
    parsed_build_final = urlparse(build_final_url)
    build_final_route = f"{parsed_build_final.path}{f'?{parsed_build_final.query}' if parsed_build_final.query else ''}"
    build_missing_markers = sorted(marker for marker in EXPECTED_BUILD_SHELL_MARKERS if marker not in build_html.text)
    if not any(marker in build_html.text for marker in EXPECTED_BUILD_SHELL_VARIANT_MARKERS):
        build_missing_markers.append("browser-app-roster|browser-preview-shell")
    build_route_holds = build_final_route == EXPECTED_BUILD_FINAL_ROUTE and not build_missing_markers
    play_shell_missing_markers = sorted(
        marker for marker in EXPECTED_PLAY_SHELL_MARKERS if marker not in play_shell_html.text
    )
    play_final_url = play_shell_html.url
    parsed_play_final = urlparse(play_final_url)
    play_final_route = f"{parsed_play_final.path}{f'?{parsed_play_final.query}' if parsed_play_final.query else ''}"
    play_shell_holds = play_final_route == "/play" and not play_shell_missing_markers
    shortcut_urls = {shortcut.get("url") for shortcut in (manifest.get("shortcuts") or []) if isinstance(shortcut, dict)}
    screenshot_count = len(manifest.get("screenshots") or [])
    has_manifest_id = manifest.get("id") == "/mobile"
    has_display_override = bool(manifest.get("display_override"))
    has_expected_shortcuts = EXPECTED_SHORTCUTS.issubset(shortcut_urls)
    has_expected_shell_cache_paths = EXPECTED_SHELL_CACHE_PATHS.issubset(precache_urls)
    ledger_stream_not_precached = PERSONALIZED_LEDGER_STREAM_ROUTE not in precache_urls
    ledger_stream_denied_by_service_worker = PERSONALIZED_LEDGER_STREAM_ROUTE in non_cacheable_paths
    ledger_stream_has_no_store_header = "no-store" in ledger_stream_cache_control.lower()
    ledger_stream_has_personalized_vary = "Cookie" in ledger_stream_vary and "Authorization" in ledger_stream_vary
    has_navigation_preload = "navigationPreload" in service_worker_text
    has_runtime_cache = "RUNTIME_CACHE" in service_worker_text
    has_push_handler = 'self.addEventListener("push"' in service_worker_text
    has_notification_click_handler = 'self.addEventListener("notificationclick"' in service_worker_text
    has_notification_close_handler = 'self.addEventListener("notificationclose"' in service_worker_text
    has_notification_route_bounds = (
        EXPECTED_NOTIFICATION_ROUTE_PATHS.issubset(notification_route_paths)
        and EXPECTED_NOTIFICATION_ROUTE_PREFIXES.issubset(notification_route_prefixes)
        and "tryNormalizeNotificationHref(" in service_worker_text
        and "isAllowedNotificationHref(" in service_worker_text
    )
    has_notification_asset_bounds = (
        EXPECTED_NOTIFICATION_ASSET_PATHS.issubset(notification_asset_paths)
        and EXPECTED_NOTIFICATION_ASSET_SUFFIXES.issubset(notification_asset_suffixes)
        and "tryNormalizeNotificationAssetPath(" in service_worker_text
        and "isAllowedNotificationAssetPath(" in service_worker_text
    )
    continuity_receipt_count = len(receipt_index.get("receipts") or [])
    continuity_boundary_present = bool(receipt_index.get("boundary"))
    mobile_json_has_routes = (
        mobile_json.get("install_route") == "/downloads"
        and mobile_json.get("continuity_route") == "/play/continuity"
        and mobile_json.get("receipt_index_route") in continuity_receipt_paths
    )
    ledger_stream_mode = ledger_stream.get("mode")
    ledger_stream_status = ledger_stream.get("status")
    ledger_stream_has_updates_route = ledger_stream.get("updates_route") == "/mobile/pwa/ledger.json"
    ledger_stream_has_valid_status = ledger_stream_status in EXPECTED_PWA_LEDGER_STATUSES
    ledger_stream_is_living_world = ledger_stream_mode == "mobile_pwa_living_world"
    ledger_stream_contract_holds = (
        isinstance(ledger_stream, dict)
        and ledger_stream_is_living_world
        and ledger_stream_has_valid_status
        and ledger_stream_has_updates_route
    )
    ledger_stream_opt_in_route = ledger_stream.get("opt_in_route")
    ledger_stream_legal_posture = str(ledger_stream.get("legal_posture") or "")
    opt_in_required_allowed_keys = {
        "mode",
        "status",
        "status_label",
        "summary",
        "legal_posture",
        "opt_in_route",
        "world_gate",
        "heat_visibility",
        "session_visibility",
        "opt_in_required_for",
        "updates_route",
        "generated_at_utc",
    }
    opt_in_required_forbidden_keys = {
        "world",
        "summary_model",
        "followed_worlds",
        "top_districts",
        "hot_district",
        "move_district",
        "tracker",
        "continuity",
    }
    opt_in_required_extra_keys = sorted(set(ledger_stream) - opt_in_required_allowed_keys) if isinstance(ledger_stream, dict) else []
    opt_in_required_leaked_keys = sorted(opt_in_required_forbidden_keys & set(ledger_stream)) if isinstance(ledger_stream, dict) else []
    ledger_stream_opt_in_boundary_holds = ledger_stream_status != "opt_in_required" or (
        ledger_stream_opt_in_route == "/account"
        and "No private run table state" in ledger_stream_legal_posture
        and "world heat" in ledger_stream_legal_posture
        and "session continuity" in ledger_stream_legal_posture
        and not opt_in_required_extra_keys
        and not opt_in_required_leaked_keys
    )
    ledger_stream_world_not_followed_boundary_holds = ledger_stream_status != "world_not_followed" or (
        isinstance(ledger_stream.get("top_districts"), list)
        and len(ledger_stream.get("top_districts") or []) == 0
        and ledger_stream.get("hot_district") is None
        and ledger_stream.get("move_district") is None
        and ledger_stream.get("continuity") is None
        and isinstance(ledger_stream.get("summary"), dict)
        and bool(ledger_stream["summary"].get("follow_hint"))
    )
    ledger_stream_live_payload_has_heat = ledger_stream_status != "live" or (
        isinstance(ledger_stream.get("world"), dict)
        and isinstance(ledger_stream.get("top_districts"), list)
        and len(ledger_stream.get("top_districts") or []) > 0
        and isinstance(ledger_stream.get("tracker"), dict)
        and ledger_stream["tracker"].get("turn_map_route") == "/ledger/map"
        and isinstance(ledger_stream.get("continuity"), dict)
    )
    live_tracker = ledger_stream.get("tracker") if isinstance(ledger_stream.get("tracker"), dict) else {}
    ledger_stream_live_actions_are_product_routes = ledger_stream_status != "live" or (
        is_public_product_route(live_tracker.get("turn_map_route"))
        and is_public_product_route(live_tracker.get("turn_route"))
        and (
            live_tracker.get("newsreel_route") is None
            or is_public_product_route(live_tracker.get("newsreel_route"))
        )
    )
    role_routes_hold = all(
        result["final_route"] == result["expected_final_route"]
        for result in route_results
    )
    route_mismatches = [
        {
            "route": result["route"],
            "final_route": result["final_route"],
            "expected_final_route": result["expected_final_route"],
        }
        for result in route_results
        if result["final_route"] != result["expected_final_route"]
    ]
    checks = [
        {"id": "mobile_page_links_manifest", "pass": has_manifest_link, "detail": "The /mobile page advertises /manifest.json."},
        {"id": "mobile_page_registers_service_worker", "pass": has_sw_registration, "detail": "The /mobile page registers the scoped service worker."},
        {"id": "mobile_page_shows_install_action", "pass": has_install_button, "detail": "The /mobile page exposes an install affordance."},
        {"id": "mobile_page_links_continuity", "pass": has_continuity_action, "detail": "The /mobile page links to /play/continuity."},
        {
            "id": "home_open_chummer_dropdown_routes_build_and_play",
            "pass": home_open_chummer_dropdown_holds,
            "detail": f"Homepage Open Chummer dropdown missing markers: {home_open_chummer_missing_markers}.",
        },
        {
            "id": "build_route_opens_character_roster",
            "pass": build_route_holds,
            "detail": (
                f"/build final route={build_final_route!r}; expected={EXPECTED_BUILD_FINAL_ROUTE!r}; "
                f"missing shell markers={build_missing_markers}."
            ),
        },
        {
            "id": "play_route_opens_pwa_play_shell",
            "pass": play_shell_holds,
            "detail": f"/play final route={play_final_route!r}; missing PWA markers={play_shell_missing_markers}.",
        },
        {"id": "manifest_id_is_mobile", "pass": has_manifest_id, "detail": f"manifest.id is {manifest.get('id')!r}."},
        {"id": "manifest_has_display_override", "pass": has_display_override, "detail": "display_override is present for richer install surfaces."},
        {"id": "manifest_shortcuts_cover_mobile_play_continuity", "pass": has_expected_shortcuts, "detail": f"shortcut URLs: {sorted(shortcut_urls)}."},
        {"id": "manifest_has_screenshots", "pass": screenshot_count >= 2, "detail": f"screenshot count: {screenshot_count}."},
        {"id": "service_worker_precaches_shell_paths", "pass": has_expected_shell_cache_paths, "detail": f"precache URLs include {sorted(EXPECTED_SHELL_CACHE_PATHS)}."},
        {"id": "ledger_stream_not_precached", "pass": ledger_stream_not_precached, "detail": "Personalized living-world data must not be in the static shell cache."},
        {"id": "ledger_stream_denied_by_service_worker_cache", "pass": ledger_stream_denied_by_service_worker, "detail": "Service worker explicitly denies /mobile/pwa/ledger.json from caching."},
        {"id": "ledger_stream_no_store", "pass": ledger_stream_has_no_store_header, "detail": f"Cache-Control: {ledger_stream_cache_control!r}."},
        {"id": "ledger_stream_varies_by_identity", "pass": ledger_stream_has_personalized_vary, "detail": f"Vary: {ledger_stream_vary!r}."},
        {"id": "service_worker_navigation_preload", "pass": has_navigation_preload, "detail": "Service worker includes navigation preload support."},
        {"id": "service_worker_runtime_cache", "pass": has_runtime_cache, "detail": "Service worker declares the runtime cache."},
        {"id": "service_worker_push_handler", "pass": has_push_handler, "detail": "Service worker handles push events."},
        {"id": "service_worker_notification_click_handler", "pass": has_notification_click_handler, "detail": "Service worker handles notification clicks."},
        {"id": "service_worker_notification_close_handler", "pass": has_notification_close_handler, "detail": "Service worker handles notification close events."},
        {"id": "notification_routes_are_bounded", "pass": has_notification_route_bounds, "detail": "Notification navigation is limited to first-party allowed routes."},
        {"id": "notification_assets_are_bounded", "pass": has_notification_asset_bounds, "detail": "Notification image assets are limited to safe local paths and suffixes."},
        {"id": "continuity_has_receipts", "pass": continuity_receipt_count >= 3, "detail": f"continuity receipt count: {continuity_receipt_count}."},
        {"id": "continuity_declares_boundary", "pass": continuity_boundary_present, "detail": "Continuity receipt index declares its privacy boundary."},
        {"id": "mobile_json_routes_hold", "pass": mobile_json_has_routes, "detail": "The PWA JSON advertises install, continuity, and receipt-index routes."},
        {"id": "ledger_stream_contract_holds", "pass": ledger_stream_contract_holds, "detail": f"ledger stream status={ledger_stream_status!r}, mode={ledger_stream_mode!r}."},
        {
            "id": "ledger_stream_opt_in_boundary_holds",
            "pass": ledger_stream_opt_in_boundary_holds,
            "detail": (
                "When opt-in is required, the ledger stream must expose only account opt-in guidance "
                f"without world, heat, tracker, followed-world, or continuity payloads. "
                f"opt_in_route={ledger_stream_opt_in_route!r}; extra_keys={opt_in_required_extra_keys}; leaked_keys={opt_in_required_leaked_keys}."
            ),
        },
        {
            "id": "ledger_stream_world_not_followed_boundary_holds",
            "pass": ledger_stream_world_not_followed_boundary_holds,
            "detail": "World-not-followed mode must hide heat, movement, turn routes, and continuity until the user follows the active world.",
        },
        {
            "id": "ledger_stream_live_payload_has_heat",
            "pass": ledger_stream_live_payload_has_heat,
            "detail": "Live mode must include a world snapshot, heat list, map route, and continuity object.",
        },
        {
            "id": "ledger_stream_live_actions_are_product_routes",
            "pass": ledger_stream_live_actions_are_product_routes,
            "detail": f"Live tracker actions must be public product routes, not raw data endpoints. tracker={live_tracker}.",
        },
        {"id": "role_routes_hold", "pass": role_routes_hold, "detail": f"route mismatches: {route_mismatches}."},
    ]
    failures = [
        f"{check['id']}: {check['detail']}"
        for check in checks
        if not check["pass"]
    ]

    payload = {
        "contract_name": "chummer.mobile_pwa_public_projection",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "checks": checks,
        "failures": failures,
        "route_results": route_results,
        "manifest": {
            "id": manifest.get("id"),
            "start_url": manifest.get("start_url"),
            "display": manifest.get("display"),
            "display_override": manifest.get("display_override"),
            "shortcut_count": len(manifest.get("shortcuts") or []),
            "icon_count": len(manifest.get("icons") or []),
            "screenshot_count": screenshot_count,
            "shortcut_urls": sorted(shortcut_urls),
        },
        "service_worker": {
            "path": service_worker_path,
            "status_code": service_worker_response.status_code,
            "has_fetch_handler": "self.addEventListener(\"fetch\"" in service_worker_text,
            "has_navigation_preload": has_navigation_preload,
            "has_runtime_cache": has_runtime_cache,
            "has_expected_shell_cache_paths": has_expected_shell_cache_paths,
            "ledger_stream_not_precached": ledger_stream_not_precached,
            "ledger_stream_denied_by_service_worker": ledger_stream_denied_by_service_worker,
            "has_push_handler": has_push_handler,
            "has_notification_click_handler": has_notification_click_handler,
            "has_notification_close_handler": has_notification_close_handler,
            "has_notification_route_bounds": has_notification_route_bounds,
            "has_notification_asset_bounds": has_notification_asset_bounds,
            "notification_route_paths": sorted(notification_route_paths),
            "notification_route_prefixes": sorted(notification_route_prefixes),
            "notification_asset_paths": sorted(notification_asset_paths),
            "notification_asset_suffixes": sorted(notification_asset_suffixes),
        },
        "page_assertions": {
            "has_manifest_link": has_manifest_link,
            "has_service_worker_registration": has_sw_registration,
            "has_install_button": has_install_button,
            "has_continuity_action": has_continuity_action,
            "role_routes_hold": role_routes_hold,
            "continuity_page_status_code": continuity_html.status_code,
        },
        "public_entry": {
            "home_open_chummer_dropdown_holds": home_open_chummer_dropdown_holds,
            "home_open_chummer_missing_markers": home_open_chummer_missing_markers,
            "build_final_url": build_final_url,
            "build_final_route": build_final_route,
            "expected_build_final_route": EXPECTED_BUILD_FINAL_ROUTE,
            "build_route_holds": build_route_holds,
            "build_missing_markers": build_missing_markers,
            "play_final_url": play_final_url,
            "play_final_route": play_final_route,
            "play_shell_holds": play_shell_holds,
            "play_shell_missing_markers": play_shell_missing_markers,
        },
        "continuity": {
            "receipt_count": continuity_receipt_count,
            "has_boundary": continuity_boundary_present,
            "mobile_json_has_routes": mobile_json_has_routes,
            "receipt_index_route": receipt_index_route,
        },
        "ledger_stream": {
            "status": ledger_stream_status,
            "mode": ledger_stream_mode,
            "has_contract": ledger_stream_contract_holds,
            "opt_in_route": ledger_stream_opt_in_route,
            "opt_in_boundary_holds": ledger_stream_opt_in_boundary_holds,
            "opt_in_required_extra_keys": opt_in_required_extra_keys,
            "opt_in_required_leaked_keys": opt_in_required_leaked_keys,
            "world_not_followed_boundary_holds": ledger_stream_world_not_followed_boundary_holds,
            "live_payload_has_heat": ledger_stream_live_payload_has_heat,
            "cache_control": ledger_stream_cache_control,
            "vary": ledger_stream_vary,
            "has_no_store_header": ledger_stream_has_no_store_header,
            "has_personalized_vary": ledger_stream_has_personalized_vary,
        },
    }
    resolved_output_path = output_path or completion_path("MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json")
    resolved_report_path = report_path or completion_path("MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.md")
    write_json(resolved_output_path, payload)
    write_text(
        resolved_report_path,
        "\n".join(
            [
                "# Mobile and PWA public projection audit",
                "",
                f"- Generated: {payload['generated_at_utc']}",
                f"- Status: `{payload['status']}`",
                f"- Manifest start URL: `{payload['manifest']['start_url']}`",
                f"- Display mode: `{payload['manifest']['display']}`",
                f"- Display override present: `{has_display_override}`",
                f"- Manifest screenshots: `{screenshot_count}`",
                f"- Manifest link present on `/mobile`: `{has_manifest_link}`",
                f"- Service worker registration present on `/mobile`: `{has_sw_registration}`",
                f"- Install action visible on `/mobile`: `{has_install_button}`",
                f"- Continuity action visible on `/mobile`: `{has_continuity_action}`",
                f"- Homepage Open Chummer dropdown routes Build and Play: `{home_open_chummer_dropdown_holds}`",
                f"- `/build` opens character roster: `{build_route_holds}`",
                f"- `/play` opens PWA play shell: `{play_shell_holds}`",
                f"- Service worker fetch handler present: `{payload['service_worker']['has_fetch_handler']}`",
                f"- Service worker navigation preload present: `{has_navigation_preload}`",
                f"- Service worker continuity cache paths present: `{has_expected_shell_cache_paths}`",
                f"- Personalized ledger stream excluded from precache: `{ledger_stream_not_precached}`",
                f"- Personalized ledger stream denied by service worker: `{ledger_stream_denied_by_service_worker}`",
                f"- Personalized ledger stream has no-store header: `{ledger_stream_has_no_store_header}`",
                f"- Personalized ledger stream varies by Cookie and Authorization: `{ledger_stream_has_personalized_vary}`",
                f"- Ledger stream opt-in boundary holds: `{ledger_stream_opt_in_boundary_holds}`",
                f"- Ledger stream world-not-followed boundary holds: `{ledger_stream_world_not_followed_boundary_holds}`",
                f"- Ledger stream live payload has heat and continuity: `{ledger_stream_live_payload_has_heat}`",
                f"- Service worker push handler present: `{has_push_handler}`",
                f"- Service worker notification click handler present: `{has_notification_click_handler}`",
                f"- Service worker notification close handler present: `{has_notification_close_handler}`",
                f"- Service worker notification route bounds present: `{has_notification_route_bounds}`",
                f"- Service worker notification asset bounds present: `{has_notification_asset_bounds}`",
                f"- Role-route redirects hold: `{role_routes_hold}`",
                f"- Continuity receipt count: `{continuity_receipt_count}`",
                f"- Continuity boundary present: `{continuity_boundary_present}`",
                "",
                "## Failures",
                "",
                *(f"- {failure}" for failure in failures),
            ]
        ),
    )
    if payload["status"] == "pass":
        print(f"mobile_pwa_public_projection:ok {resolved_output_path}")
    else:
        print(f"mobile_pwa_public_projection:fail {resolved_output_path}")
        for failure in failures:
            print(f"- {failure}")
    return 0 if payload["status"] == "pass" else 1


def main() -> int:
    args = parse_args()
    output_path, report_path = resolve_output_paths(args.completion_dir, args.output, args.report)
    if args.base_url:
        return run(args.base_url, output_path=output_path, report_path=report_path)

    with LocalHubApp() as app:
        return run(app.base_url, output_path=output_path, report_path=report_path)


if __name__ == "__main__":
    raise SystemExit(main())
