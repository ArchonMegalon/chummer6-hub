#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

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
ROLE_SHELLS = {
    "player": (
        "/play?role=player",
        "/manifest.player.webmanifest",
        "Chummer Player",
        "Keep your runner ready at the table.",
        "Runner readiness",
        "/mobile/player",
    ),
    "gm": (
        "/play?role=gm",
        "/manifest.gm.webmanifest",
        "Chummer GM",
        "Stage the table without exposing Game Master controls.",
        "Scene pacing",
        "/mobile/gm",
    ),
    "observer": (
        "/play?role=observer",
        "/manifest.observer.webmanifest",
        "Chummer Observer",
        "Follow the table without gaining control.",
        "Read-mostly return",
        "/mobile/observer",
    ),
}
ROLE_PROBES = (
    ("player", "/play?role=player", "player"),
    ("gm", "/play?role=gm", "gm"),
    ("observer", "/play?role=observer", "observer"),
    ("gm_secret_extra", "/play?role=gm&secret=must-not-survive&extra=1", "gm"),
    ("repeated_roles", "/play?role=gm&role=observer&token=must-not-survive", "player"),
    ("unknown_role", "/play?role=owner&access_token=must-not-survive", "player"),
    ("mixed_case_alias", "/play?role=GaMe-MaStEr&api_key=must-not-survive", "gm"),
    ("missing_role_with_secret", "/play?secret=must-not-survive&extra=1", "player"),
)
SENSITIVE_REDIRECT_MARKERS = ("secret", "token", "access_token", "api_key", "must-not-survive")


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the local install-only mobile PWA public edge.")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--source-root", type=Path, default=RUN_SERVICES_ROOT)
    parser.add_argument("--mobile-release-proof", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run(
        args.base_url,
        args.mobile_release_proof,
        source_root=args.source_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
