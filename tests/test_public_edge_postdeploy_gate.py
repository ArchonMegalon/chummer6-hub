from __future__ import annotations

import importlib.util
import json
import types
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_public_edge_postdeploy_gate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_public_edge_postdeploy_gate", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def passing_receipts():
    return (
        {
            "contractName": "chummer.public_edge_deploy_preflight.v1",
            "status": "pass",
            "overlayRoot": "/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app",
            "overlayBuildInfoSourceFingerprint": {
                "aggregateMatchesCurrentSource": True,
                "recordedAggregateSha256": "a" * 64,
                "expectedAggregateSha256": "a" * 64,
                "recordedFullDeploymentDigestSha256": "b" * 64,
                "expectedFullDeploymentDigestSha256": "b" * 64,
                "missingKeys": [],
                "mismatchedKeys": [],
            },
            "publicPwaStaticProof": {
                "status": "pass",
                "assetDigestInventory": {
                    "contractName": "chummer.public_pwa_asset_digest_inventory.v1",
                    "assetCount": 14,
                    "sha256": "c" * 64,
                },
            },
            "activeLockCount": 0,
            "foreignLockCount": 0,
            "ignoredForeignLockCount": 0,
            "staleLookingLockCount": 0,
            "foreignLocksIgnored": False,
            "allowForeignBuildLocks": False,
            "staleForeignLockCount": 0,
            "staleForeignLocksIgnored": False,
            "allowStaleForeignBuildLocks": False,
            "findings": [],
        },
        {
            "contractName": "chummer.downloads_version_marker.v1",
            "status": "pass",
            "base_url": "https://chummer.run",
            "downloads_has_marker": True,
            "status_redirect_has_marker": True,
            "status_redirect_heading": "Stable downloads",
            "status_redirect_heading_recognized": True,
            "status_redirect_heading_expected": "Stable downloads",
            "status_redirect_heading_matches_release_channel": True,
            "status_redirect_heading_uses_generic_updated_copy": False,
            "visible_version": "Version run-20260630",
            "status_redirect_version": "Version run-20260630",
            "downloads_version_marker_value": "Version run-20260630",
            "status_redirect_version_marker_value": "Version run-20260630",
            "downloads_version_marker_matches_release_channel": True,
            "status_redirect_version_marker_matches_release_channel": True,
            "visible_version_matches_release_channel": True,
            "status_redirect_version_matches_release_channel": True,
            "expected_release_status": "published",
            "expected_release_channel": "public_stable",
            "expected_release_supportability_state": "gold_supported",
            "expected_release_rollout_state": "public_stable",
            "release_manifest_http_status": 200,
            "release_manifest_status": "published",
            "release_manifest_status_matches_release_channel": True,
            "release_manifest_channel": "public_stable",
            "release_manifest_channel_matches_release_channel": True,
            "release_manifest_version": "run-20260630",
            "release_manifest_version_matches_release_channel": True,
            "release_manifest_supportability_state": "gold_supported",
            "release_manifest_supportability_matches_release_channel": True,
            "release_manifest_rollout_state": "public_stable",
            "release_manifest_rollout_matches_release_channel": True,
            "public_release_copy_safe": True,
            "public_release_unsafe_copy_markers": [],
            "public_release_has_preview_or_review_caveat": False,
            "release_manifest_copy_safe": True,
            "release_manifest_unsafe_copy_markers": [],
            "release_manifest_has_preview_or_review_caveat": False,
            "release_manifest_parse_error": None,
        },
        {
            "contractName": "chummer.public_pwa_static_assets.v1",
            "status": "pass",
            "base_url": "https://chummer.run",
            "manifests": [{}, {}, {}],
            "role_manifests": [
                {
                    "path": "/manifest.player.webmanifest",
                    "role": "Player",
                    "id": "/mobile/player",
                    "start_url": "/mobile/player",
                    "display": "standalone",
                },
                {
                    "path": "/manifest.gm.webmanifest",
                    "role": "GameMaster",
                    "id": "/mobile/gm",
                    "start_url": "/mobile/gm",
                    "display": "standalone",
                },
            ],
            "assets": [{} for _ in range(11)],
            "assetDigestInventory": {
                "sealedExpectedSha256": "c" * 64,
                "matchesExpected": True,
                "sourceStable": True,
            },
            "service_worker": {
                "worker_kind": "play",
                "cache_version": "play-shell-v16",
                "ledger_stream_non_cacheable": True,
                "ledger_stream_precached": False,
            },
            "deploymentIdentity": {
                "ready": True,
                "code": "overlay_identity_bound",
                "sourceFingerprintSha256": "a" * 64,
                "fullDeploymentDigestSha256": "b" * 64,
                "matchesExpectedFullDeploymentDigest": True,
            },
        },
        {
            "contractName": "chummer.mobile_pwa_ledger_boundary.v1",
            "status": "pass",
            "base_url": "https://chummer.run",
            "payload_status": "opt_in_required",
            "cache_control": "private, no-store, no-cache, max-age=0",
            "vary": "Cookie, Authorization",
        },
        {
            "contractName": "chummer.ready_mobile_handoff_contract.v1",
            "status": "pass",
            "base_url": "https://chummer.run",
            "tool_ids": ["inventory", "health", "ammo", "modifiers", "quick_rolls", "living_world"],
            "packet_roles": ["player", "gm", "organizer"],
            "frontdoor_launch_route": "/mobile/player",
            "role_routes": [
                {
                    "role": "Player",
                    "mode": "player",
                    "route": "/mobile/player",
                    "manifest_path": "/manifest.player.webmanifest",
                    "manifest_id": "/mobile/player",
                    "manifest_start_url": "/mobile/player?role=Player",
                    "session_handoff_route_template": "/mobile/player?sessionId={sessionId}&role=Player",
                    "frontdoor_default": True,
                },
                {
                    "role": "GameMaster",
                    "mode": "gm",
                    "route": "/mobile/gm",
                    "manifest_path": "/manifest.gm.webmanifest",
                    "manifest_id": "/mobile/gm",
                    "manifest_start_url": "/mobile/gm?role=GameMaster",
                    "session_handoff_route_template": "/mobile/gm?sessionId={sessionId}&role=GameMaster",
                    "frontdoor_default": False,
                },
            ],
        },
        {
            "contractName": "chummer.participate_iframe_shell.v1",
            "status": "pass",
            "base_url": "https://chummer.run",
            "route_count": 2,
            "iframe_route_count": 2,
            "offline_fallback_route_count": 0,
        },
    )


def passing_role_alias_routes() -> dict[str, object]:
    def first_hop(method: str, target: str) -> dict[str, object]:
        return {
            "method": method,
            "status": 302,
            "location": f"{target}#",
            "cacheControl": "private, no-store, no-cache, max-age=0",
            "pragma": "no-cache",
            "expires": "0",
            "referrerPolicy": "no-referrer",
            "checks": {
                "exact302": True,
                "exactLocation": True,
                "privateNoCache": True,
                "pragmaNoCache": True,
                "expiresZero": True,
                "noReferrer": True,
                "requestSucceeded": True,
            },
            "pass": True,
            "error": "",
        }

    def alias_result(alias: str, target: str) -> dict[str, object]:
        return {
            "aliasPath": alias,
            "requestedUrl": (
                f"https://chummer.run{alias}"
                "?sessionId=[redacted]&deviceId=[redacted]"
            ),
            "expectedFirstHopLocation": f"{target}#",
            "firstHopResults": [first_hop("GET", target), first_hop("HEAD", target)],
            "httpStatus": 200,
            "finalUrl": f"https://chummer.run{target}",
            "finalRoute": target,
            "canonicalTarget": {
                "route": target,
                "status": 200,
                "contentType": "text/html; charset=utf-8",
                "cacheControl": "private, no-store, no-cache, max-age=0",
                "pragma": "no-cache",
                "expires": "0",
                "referrerPolicy": "no-referrer",
                "contentTypeOptions": "nosniff",
                "bodyBytesRead": 72,
                "responseUrlExact": True,
                "noRedirectLocation": True,
                "bodyWithinLimit": True,
                "installOnlyShell": True,
                "pass": True,
                "error": "",
            },
            "expectedFinalRoute": target,
            "firstHopsPass": True,
            "finalUrlPass": True,
            "pass": True,
            "error": "",
        }

    return {
        "contractName": "chummer.public_role_alias_routes.v1",
        "status": "pass",
        "baseUrl": "https://chummer.run",
        "results": [
            alias_result("/player", "/mobile/player"),
            alias_result("/jammer", "/mobile/player"),
            alias_result("/gm", "/mobile/gm"),
            alias_result("/observer", "/mobile/observer"),
        ],
        "drift": [],
    }


def test_role_alias_probe_requires_jammer_and_a_discarded_synthetic_query(monkeypatch) -> None:
    module = load_module()
    seen_urls: list[str] = []
    expected_targets = {
        "/player": "/mobile/player",
        "/jammer": "/mobile/player",
        "/gm": "/mobile/gm",
        "/observer": "/mobile/observer",
    }

    class Response:
        def __init__(
            self,
            status: int,
            final_url: str,
            headers: dict[str, str] | None = None,
            body: bytes = b"",
        ) -> None:
            self.status = status
            self._final_url = final_url
            self.headers = headers or {}
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def geturl(self) -> str:
            return self._final_url

        def read(self, amount: int = -1) -> bytes:
            return self._body if amount < 0 else self._body[:amount]

        def close(self) -> None:
            return None

    def redirect_headers(target: str) -> dict[str, str]:
        return {
            "Location": f"{target}#",
            "Cache-Control": "private, no-store, no-cache, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Referrer-Policy": "no-referrer",
        }

    seen_first_hops: list[tuple[str, str]] = []

    def fake_first_hop(request, timeout):  # noqa: ANN001, ARG001
        alias_path = module.urlparse(request.full_url).path
        seen_first_hops.append((request.method, request.full_url))
        return Response(302, request.full_url, redirect_headers(expected_targets[alias_path]))

    def fake_canonical_target(request, timeout):  # noqa: ANN001, ARG001
        seen_urls.append(request.full_url)
        return Response(
            200,
            request.full_url,
            _alias_canonical_headers(),
            _alias_install_shell_body(),
        )

    monkeypatch.setattr(module, "open_role_alias_first_hop", fake_first_hop)
    monkeypatch.setattr(
        module,
        "open_role_alias_canonical_target",
        fake_canonical_target,
    )

    receipt = module.probe_role_alias_routes("https://chummer.run", 2)

    assert receipt["status"] == "pass"
    assert {row["aliasPath"] for row in receipt["results"]} == set(expected_targets)
    assert {method for method, _ in seen_first_hops} == {"GET", "HEAD"}
    assert len(seen_first_hops) == len(expected_targets) * 2
    assert all("?sessionId=synthetic-role-alias-proof" in url for _, url in seen_first_hops)
    assert all("&deviceId=synthetic-role-alias-proof" in url for _, url in seen_first_hops)
    assert len(seen_urls) == len(expected_targets)
    assert all(not module.urlparse(url).query for url in seen_urls)
    assert sorted(module.urlparse(url).path for url in seen_urls) == sorted(expected_targets.values())
    assert all(row["finalRoute"] == expected_targets[row["aliasPath"]] for row in receipt["results"])
    assert all(row["firstHopsPass"] is True for row in receipt["results"])
    assert all(row["finalUrlPass"] is True for row in receipt["results"])
    serialized = json.dumps(receipt)
    assert "synthetic-role-alias-proof" not in serialized
    assert "sessionId=[redacted]" in serialized
    assert "deviceId=[redacted]" in serialized


def test_role_alias_first_hop_opener_deliberately_returns_unfollowed_302(monkeypatch) -> None:
    module = load_module()
    response = module.HTTPError(
        "https://chummer.run/jammer?sessionId=synthetic-role-alias-proof",
        302,
        "Found",
        {"Location": "/mobile/player#"},
        None,
    )
    captured_handlers: list[object] = []

    class Opener:
        def open(self, request, timeout):  # noqa: ANN001, ARG002
            raise response

    def fake_build_opener(handler):  # noqa: ANN001
        captured_handlers.append(handler)
        return Opener()

    monkeypatch.setattr(module, "build_opener", fake_build_opener)

    observed = module.open_role_alias_first_hop(
        module.Request("https://chummer.run/jammer", method="GET"),
        2,
    )

    assert observed is response
    assert len(captured_handlers) == 1
    assert isinstance(captured_handlers[0], module._RoleAliasNoRedirectHandler)
    assert captured_handlers[0].redirect_request(None, None, 302, "Found", {}, "/mobile/player#") is None


class _AliasProbeResponse:
    def __init__(
        self,
        status: int,
        final_url: str,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> None:
        self.status = status
        self._final_url = final_url
        self.headers = headers or {}
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def geturl(self) -> str:
        return self._final_url

    def read(self, amount: int = -1) -> bytes:
        return self._body if amount < 0 else self._body[:amount]

    def close(self) -> None:
        return None


def _alias_redirect_headers(target: str) -> dict[str, str]:
    return {
        "Location": f"{target}#",
        "Cache-Control": "private, no-store, no-cache, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "Referrer-Policy": "no-referrer",
    }


def _alias_canonical_headers(**overrides: str) -> dict[str, str]:
    headers = {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "private, no-store, no-cache, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
    }
    headers.update(overrides)
    return headers


def _alias_install_shell_body() -> bytes:
    return b'<html><body><main data-play-surface="install-only"></main></body></html>'


@pytest.mark.parametrize(
    ("mutation", "bad_value"),
    [
        ("status", 301),
        ("location", "/mobile/player/extra#"),
        ("location", "https://attacker.example/mobile/player#"),
        ("location", "/mobile/player?sessionId=synthetic-role-alias-proof#"),
        ("location", "/mobile/player"),
        ("cache", "private, no-store, max-age=0"),
        ("pragma", "store"),
        ("expires", "-1"),
        ("referrer", "origin"),
    ],
)
def test_role_alias_probe_rejects_malicious_first_hop_contract(
    monkeypatch,
    mutation: str,
    bad_value: object,
) -> None:
    module = load_module()
    expected_targets = {
        "/player": "/mobile/player",
        "/jammer": "/mobile/player",
        "/gm": "/mobile/gm",
        "/observer": "/mobile/observer",
    }
    canonical_requests: list[str] = []

    def fake_first_hop(request, timeout):  # noqa: ANN001, ARG001
        alias_path = module.urlparse(request.full_url).path
        target = expected_targets[alias_path]
        headers = _alias_redirect_headers(target)
        status = 302
        if alias_path == "/jammer" and request.method == "GET":
            if mutation == "status":
                status = int(bad_value)
            elif mutation == "location":
                headers["Location"] = str(bad_value)
            elif mutation == "cache":
                headers["Cache-Control"] = str(bad_value)
            elif mutation == "pragma":
                headers["Pragma"] = str(bad_value)
            elif mutation == "expires":
                headers["Expires"] = str(bad_value)
            elif mutation == "referrer":
                headers["Referrer-Policy"] = str(bad_value)
        return _AliasProbeResponse(status, request.full_url, headers)

    def fake_canonical_target(request, timeout):  # noqa: ANN001, ARG001
        canonical_requests.append(request.full_url)
        return _AliasProbeResponse(
            200,
            request.full_url,
            _alias_canonical_headers(),
            _alias_install_shell_body(),
        )

    monkeypatch.setattr(module, "open_role_alias_first_hop", fake_first_hop)
    monkeypatch.setattr(module, "open_role_alias_canonical_target", fake_canonical_target)

    receipt = module.probe_role_alias_routes("https://chummer.run", 2)
    jammer = next(row for row in receipt["results"] if row["aliasPath"] == "/jammer")

    assert receipt["status"] == "fail"
    assert jammer["firstHopsPass"] is False
    assert jammer["pass"] is False
    assert len(canonical_requests) == len(expected_targets) - 1
    assert all(not module.urlparse(url).query for url in canonical_requests)
    assert "synthetic-role-alias-proof" not in json.dumps(receipt)


@pytest.mark.parametrize(
    "bad_final_url",
    [
        "https://attacker.example/mobile/player#",
        "https://chummer.run.attacker.example/mobile/player#",
        "http://chummer.run/mobile/player#",
        "https://chummer.run:444/mobile/player#",
        "https://user:secret@chummer.run/mobile/player#",
        "https://chummer.run/mobile/player/extra#",
        "https://chummer.run/mobile/player?sessionId=synthetic-role-alias-proof#",
        "https://chummer.run/mobile/player#private",
    ],
)
def test_role_alias_probe_rejects_unclean_or_cross_origin_final_url(
    monkeypatch,
    bad_final_url: str,
) -> None:
    module = load_module()
    expected_targets = {
        "/player": "/mobile/player",
        "/jammer": "/mobile/player",
        "/gm": "/mobile/gm",
        "/observer": "/mobile/observer",
    }

    def fake_first_hop(request, timeout):  # noqa: ANN001, ARG001
        alias_path = module.urlparse(request.full_url).path
        return _AliasProbeResponse(
            302,
            request.full_url,
            _alias_redirect_headers(expected_targets[alias_path]),
        )

    canonical_call_count = 0

    def fake_canonical_target(request, timeout):  # noqa: ANN001, ARG001
        nonlocal canonical_call_count
        canonical_call_count += 1
        target_path = module.urlparse(request.full_url).path
        final_url = (
            bad_final_url
            if target_path == "/mobile/player" and canonical_call_count == 2
            else request.full_url
        )
        return _AliasProbeResponse(
            200,
            final_url,
            _alias_canonical_headers(),
            _alias_install_shell_body(),
        )

    monkeypatch.setattr(module, "open_role_alias_first_hop", fake_first_hop)
    monkeypatch.setattr(module, "open_role_alias_canonical_target", fake_canonical_target)

    receipt = module.probe_role_alias_routes("https://chummer.run", 2)
    jammer = next(row for row in receipt["results"] if row["aliasPath"] == "/jammer")

    assert receipt["status"] == "fail"
    assert jammer["firstHopsPass"] is True
    assert jammer["finalUrlPass"] is False
    assert jammer["pass"] is False
    assert "synthetic-role-alias-proof" not in json.dumps(receipt)


def test_role_alias_probe_redacts_synthetic_values_from_errors(monkeypatch) -> None:
    module = load_module()

    def fail_first_hop(request, timeout):  # noqa: ANN001, ARG001
        raise module.URLError(
            f"first-hop failure for {module.ROLE_ALIAS_SYNTHETIC_PRIVATE_VALUE}"
        )

    def fail_canonical_target(request, timeout):  # noqa: ANN001, ARG001
        raise module.URLError(
            f"follow failure for {module.ROLE_ALIAS_SYNTHETIC_PRIVATE_VALUE}"
        )

    monkeypatch.setattr(module, "open_role_alias_first_hop", fail_first_hop)
    monkeypatch.setattr(
        module,
        "open_role_alias_canonical_target",
        fail_canonical_target,
    )

    receipt = module.probe_role_alias_routes("https://chummer.run", 2)
    serialized = json.dumps(receipt)

    assert receipt["status"] == "fail"
    assert module.ROLE_ALIAS_SYNTHETIC_PRIVATE_VALUE not in serialized
    assert "[redacted]" in serialized


@pytest.mark.parametrize("failure_kind", ["blank", "oversized", "redirect-loop"])
def test_role_alias_probe_rejects_invalid_canonical_install_shell(
    monkeypatch,
    failure_kind: str,
) -> None:
    module = load_module()
    expected_targets = {
        "/player": "/mobile/player",
        "/jammer": "/mobile/player",
        "/gm": "/mobile/gm",
        "/observer": "/mobile/observer",
    }

    def fake_first_hop(request, timeout):  # noqa: ANN001, ARG001
        alias_path = module.urlparse(request.full_url).path
        return _AliasProbeResponse(
            302,
            request.full_url,
            _alias_redirect_headers(expected_targets[alias_path]),
        )

    def fake_canonical_target(request, timeout):  # noqa: ANN001, ARG001
        target_path = module.urlparse(request.full_url).path
        if target_path != "/mobile/player":
            return _AliasProbeResponse(
                200,
                request.full_url,
                _alias_canonical_headers(),
                _alias_install_shell_body(),
            )
        if failure_kind == "redirect-loop":
            return _AliasProbeResponse(
                302,
                request.full_url,
                _alias_redirect_headers("/mobile/player"),
            )
        body = (
            b"<html><body><main></main></body></html>"
            if failure_kind == "blank"
            else b"x" * (module.ROLE_ALIAS_CANONICAL_MAX_BODY_BYTES + 1)
        )
        return _AliasProbeResponse(
            200,
            request.full_url,
            _alias_canonical_headers(),
            body,
        )

    monkeypatch.setattr(module, "open_role_alias_first_hop", fake_first_hop)
    monkeypatch.setattr(module, "open_role_alias_canonical_target", fake_canonical_target)

    receipt = module.probe_role_alias_routes("https://chummer.run", 2)
    player = next(row for row in receipt["results"] if row["aliasPath"] == "/player")

    assert receipt["status"] == "fail"
    assert player["canonicalTarget"]["pass"] is False
    assert player["pass"] is False
    if failure_kind == "blank":
        assert player["canonicalTarget"]["installOnlyShell"] is False
    elif failure_kind == "oversized":
        assert player["canonicalTarget"]["bodyWithinLimit"] is False
        assert player["canonicalTarget"]["bodyBytesRead"] == module.ROLE_ALIAS_CANONICAL_MAX_BODY_BYTES + 1
    else:
        assert player["canonicalTarget"]["status"] == 302
        assert player["canonicalTarget"]["noRedirectLocation"] is False
    assert module.ROLE_ALIAS_SYNTHETIC_PRIVATE_VALUE not in json.dumps(receipt)


def test_role_alias_probe_never_contacts_off_origin_redirect_target() -> None:
    module = load_module()
    attacker_requests: list[str] = []

    class AttackerHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            attacker_requests.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    attacker = ThreadingHTTPServer(("127.0.0.1", 0), AttackerHandler)
    attacker_thread = threading.Thread(target=attacker.serve_forever, daemon=True)
    attacker_thread.start()
    attacker_url = f"http://127.0.0.1:{attacker.server_address[1]}"

    expected_targets = {
        "/player": "/mobile/player",
        "/jammer": "/mobile/player",
        "/gm": "/mobile/gm",
        "/observer": "/mobile/observer",
    }

    class TrustedHandler(BaseHTTPRequestHandler):
        def do_HEAD(self) -> None:  # noqa: N802
            self._respond(include_body=False)

        def do_GET(self) -> None:  # noqa: N802
            self._respond(include_body=True)

        def _respond(self, *, include_body: bool) -> None:
            request_path = module.urlparse(self.path).path
            if request_path in expected_targets:
                target = expected_targets[request_path]
                if request_path == "/jammer":
                    target = f"{attacker_url}/mobile/player"
                self.send_response(302)
                for name, value in _alias_redirect_headers(target).items():
                    self.send_header(name, value)
                self.end_headers()
                return
            if request_path in set(expected_targets.values()):
                body = _alias_install_shell_body()
                self.send_response(200)
                for name, value in _alias_canonical_headers(
                    **{"Content-Length": str(len(body))}
                ).items():
                    self.send_header(name, value)
                self.end_headers()
                if include_body:
                    self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    trusted = ThreadingHTTPServer(("127.0.0.1", 0), TrustedHandler)
    trusted_thread = threading.Thread(target=trusted.serve_forever, daemon=True)
    trusted_thread.start()

    try:
        receipt = module.probe_role_alias_routes(
            f"http://127.0.0.1:{trusted.server_address[1]}",
            2,
        )
    finally:
        trusted.shutdown()
        trusted.server_close()
        trusted_thread.join(timeout=5)
        attacker.shutdown()
        attacker.server_close()
        attacker_thread.join(timeout=5)

    jammer = next(row for row in receipt["results"] if row["aliasPath"] == "/jammer")
    assert receipt["status"] == "fail"
    assert jammer["firstHopsPass"] is False
    assert jammer["canonicalTarget"]["status"] == 0
    assert attacker_requests == []
    serialized = json.dumps(receipt)
    assert attacker_url not in serialized
    assert module.ROLE_ALIAS_SYNTHETIC_PRIVATE_VALUE not in serialized


def passing_online_launch_receipt() -> dict[str, object]:
    return {
        "contractName": "chummer.online_character_roster_launch.v1",
        "status": "pass",
        "launch_url": "https://chummer.run/app?command=character_roster",
        "final_url": "https://chummer.run/blazor/app?command=character_roster",
        "http_status": 200,
        "has_blazor_marker": True,
        "has_roster_marker": True,
    }


def passing_online_launch_direct_receipt() -> dict[str, object]:
    receipt = passing_online_launch_receipt()
    receipt["final_url"] = "https://chummer.run/app?command=character_roster"
    return receipt


def passing_mobile_pwa_viewport_artifact(module) -> dict[str, object]:  # noqa: ANN001
    routes = sorted(module.REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES)
    results: list[dict[str, object]] = []
    for viewport, expectation in module.REQUIRED_MOBILE_PWA_VIEWPORTS.items():
        for route in routes:
            result: dict[str, object] = {
                "route": route,
                "viewport": viewport,
                "width": expectation["width"],
                "height": expectation["height"],
                "status": 200,
                "overflow_x": 0,
                "navigation_error": "",
            }
            if route == "/build":
                expected_layout = expectation["buildLayout"]
                result.update(
                    {
                        "final_url": "https://chummer.run/blazor/app?command=character_roster",
                        "build_layout_source": "browser-media-query",
                        "build_layout_preference": "auto",
                        "build_layout_effective": expected_layout,
                        "build_layout_override_checked": (
                            "workspace"
                            if expected_layout == "compact"
                            else "compact"
                        ),
                    }
                )
            results.append(result)
    return {
        "contractName": "chummer.mobile_pwa_viewport_smoke.v1",
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "pass",
        "base_url": "https://chummer.run",
        "routes": routes,
        "route_count": len(routes),
        "viewport_count": len(module.REQUIRED_MOBILE_PWA_VIEWPORTS),
        "results": results,
        "failures": [],
    }


def passing_mobile_pwa_viewport_browser_proof(module) -> dict[str, object]:  # noqa: ANN001
    return {
        "status": "pass",
        "exitCode": 0,
        "artifactDir": "/tmp/chummer-mobile-pwa-viewport",
        "artifactBaseUrlMatchesRequested": True,
        "artifactCurrentContractSatisfied": True,
        "artifactContractFailures": [],
        "artifact": passing_mobile_pwa_viewport_artifact(module),
    }


def passing_pwa_offline_browser_proof() -> dict[str, object]:
    return {
        "status": "pass",
        "exitCode": 0,
        "artifactDir": "/tmp/chummer-pwa-offline-cache",
        "artifact": {
            "contractName": "chummer.pwa_offline_cache.v2",
            "status": "pass",
            "cache_version": "v17",
            "navigation_policy": "network_only",
            "private_state_scope": "open_tab_only",
            "query_bearing_requests_cached": False,
            "private_navigation_cached": False,
            "private_api_cached": False,
            "personalized_ledger_cached": False,
            "legacy_private_cache_prefixes_purged": [
                "chummer-shell-play-shell-",
                "chummer-media-play-shell-",
                "chummer-media-meta-play-shell-",
            ],
            "unrelated_cache_preserved": True,
            "static_paths": [
                "/manifest.player.webmanifest",
                "/manifest.gm.webmanifest",
                "/mobile.css",
                "/mobile-turn-companion.js",
            ],
            "offline_role_fallbacks": [
                {
                    "role": "Player",
                    "path": "/mobile/player",
                    "status": 503,
                    "cache_control": "private, no-store",
                    "private_projection_restored": False,
                },
                {
                    "role": "GameMaster",
                    "path": "/mobile/gm",
                    "status": 503,
                    "cache_control": "private, no-store",
                    "private_projection_restored": False,
                },
            ],
        },
    }


def passing_frontdoor_navigation(homepage_lane_text: str = "Current public lane: Stable.") -> dict[str, object]:
    redacted = "%5Bredacted%5D"
    return {
        "status": "pass",
        "exitCode": 0,
        "artifactDir": "/tmp/chummer-frontdoor-navigation",
        "mobileArtifact": {
            "contractName": "chummer.frontdoor_mobile_launch.v2",
            "status": "pass",
            "base_url": "https://chummer.run",
            "gated_targets": ["Build", "Play"],
            "public_targets": [],
            "homepage_lane_text": homepage_lane_text,
            "play_route": "/mobile/player",
            "play_sign_in_route": "/login?next=%2Fmobile%2Fplayer",
            "direct_player_http_status": 200,
            "direct_player_route": "/mobile/player",
            "final_url": "https://chummer.run/mobile/player",
            "private_identity_redacted": True,
            "visible_player_url_private_identity_absent": True,
            "player_session_context_present": True,
            "player_device_context_present": True,
            "live_turn_companion_shell": True,
            "pwa_manifest_path": "/manifest.player.webmanifest",
            "pwa_role": "Player",
            "blazor_shell": "interactive-server",
            "rybbit_configured": True,
            "rybbit_tag": "mobile_play_shell",
            "rybbit_route": "/mobile/player",
            "rybbit_mode": "player",
            "rybbit_role": "Player",
            "rybbit_site_id_present": True,
            "rybbit_script_url_present": True,
            "rybbit_script_url_allowed": True,
            "rybbit_skip_patterns": ["/mobile/**"],
            "rybbit_mask_patterns": ["/api/play/**", "/mobile/**"],
            "rybbit_skip_mobile_paths": True,
            "rybbit_mask_mobile_paths": True,
            "rybbit_masks_private_play_routes": True,
            "rybbit_replay_block_selector": "[data-turn-root]",
            "rybbit_replay_blocks_turn_root": True,
            "player_session_handoff_url": f"https://chummer.run/mobile/player?sessionId={redacted}&role=Player",
            "player_session_handoff_status": "Session handoff is ready in the link above.",
            "player_session_handoff_link_text": "Open session handoff link",
            "player_session_handoff_preserves_session": True,
            "player_session_handoff_preserves_role": True,
            "player_session_handoff_strips_device": True,
            "player_session_handoff_sender_device_id_present": True,
            "player_session_handoff_private_identity_redacted": True,
            "gm_route": "/mobile/gm",
            "gm_route_session_id_present": True,
            "gm_route_private_identity_redacted": True,
            "gm_http_status": 200,
            "gm_final_url": "https://chummer.run/mobile/gm",
            "visible_gm_url_private_identity_absent": True,
            "gm_session_context_present": True,
            "gm_device_context_present": True,
            "gm_live_turn_companion_shell": True,
            "gm_pwa_manifest_path": "/manifest.gm.webmanifest",
            "gm_pwa_role": "GameMaster",
            "gm_blazor_shell": "interactive-server",
            "gm_rybbit_configured": True,
            "gm_rybbit_tag": "mobile_play_shell",
            "gm_rybbit_route": "/mobile/gm",
            "gm_rybbit_mode": "gm",
            "gm_rybbit_role": "GameMaster",
            "gm_rybbit_site_id_present": True,
            "gm_rybbit_script_url_present": True,
            "gm_rybbit_script_url_allowed": True,
            "gm_rybbit_skip_patterns": ["/mobile/**"],
            "gm_rybbit_mask_patterns": ["/api/play/**", "/mobile/**"],
            "gm_rybbit_skip_mobile_paths": True,
            "gm_rybbit_mask_mobile_paths": True,
            "gm_rybbit_masks_private_play_routes": True,
            "gm_rybbit_replay_block_selector": "[data-turn-root]",
            "gm_rybbit_replay_blocks_turn_root": True,
            "gm_session_handoff_url": f"https://chummer.run/mobile/gm?sessionId={redacted}&role=GameMaster",
            "gm_session_handoff_status": "Session handoff is ready in the link above.",
            "gm_session_handoff_link_text": "Open session handoff link",
            "gm_session_handoff_preserves_session": True,
            "gm_session_handoff_preserves_role": True,
            "gm_session_handoff_strips_device": True,
            "gm_session_handoff_sender_device_id_present": True,
            "gm_session_handoff_private_identity_redacted": True,
        },
        "ledgerArtifact": {
            "contractName": "chummer.black_ledger_globe_frontdoor.v1",
            "status": "pass",
            "base_url": "https://chummer.run",
            "ledger_primary": False,
        },
        "anchorArtifact": {
            "contractName": "chummer.frontdoor_mobile_anchor_redirect.v2",
            "status": "pass",
            "base_url": "https://chummer.run",
            "entry_url": "https://chummer.run/#turn-runsite-card",
            "final_url": "https://chummer.run/mobile/player#turn-runsite-card",
            "final_pathname": "/mobile/player",
            "final_hash": "#turn-runsite-card",
            "pwa_manifest_path": "/manifest.player.webmanifest",
            "pwa_role": "Player",
            "blazor_shell": "interactive-server",
            "private_identity_redacted": True,
            "visible_url_private_identity_absent": True,
            "session_context_present": True,
            "device_context_present": True,
            "failure": "",
        },
    }


def write_passing_frontdoor_artifacts(
    artifact_dir: Path,
    *,
    homepage_lane_text: str = "Current public lane: Stable.",
    anchor_entry_url: str = "https://chummer.run/#turn-runsite-card",
) -> None:
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    proof = passing_frontdoor_navigation(homepage_lane_text)
    artifacts = (
        ("FRONTDOOR_MOBILE_LAUNCH.generated.json", proof["mobileArtifact"]),
        ("BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json", proof["ledgerArtifact"]),
        ("FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json", proof["anchorArtifact"]),
    )
    for file_name, artifact_value in artifacts:
        artifact = dict(artifact_value)  # type: ignore[arg-type]
        artifact["generated_at_utc"] = generated_at
        if file_name == "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json":
            artifact["entry_url"] = anchor_entry_url
        (artifact_dir / file_name).write_text(json.dumps(artifact), encoding="utf-8")


def test_postdeploy_gate_passes_when_all_child_receipts_pass() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
        role_alias_routes=passing_role_alias_routes(),
        online_launch=passing_online_launch_receipt(),
        expected_full_deployment_digest_sha256="b" * 64,
    )

    assert result["status"] == "pass"
    assert result["baseUrl"] == "https://chummer.run"
    assert result["expectedReleaseVersion"] == "run-20260630"
    assert result["preflightOverlayRoot"] == "/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app"
    assert result["preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource"] is True
    assert result["preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256"] == "a" * 64
    assert result["preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256"] == "a" * 64
    assert result["preflightOverlayBuildInfoSourceFingerprintMissingKeys"] == []
    assert result["preflightOverlayBuildInfoSourceFingerprintMismatchedKeys"] == []
    assert result["visibleVersionMatchesReleaseChannel"] is True
    assert result["statusRedirectVersion"] == "Version run-20260630"
    assert result["statusRedirectVersionMatchesReleaseChannel"] is True
    assert result["expectedReleaseStatus"] == "published"
    assert result["expectedReleaseChannel"] == "public_stable"
    assert result["releaseManifestStatus"] == "published"
    assert result["releaseManifestStatusMatchesReleaseChannel"] is True
    assert result["releaseManifestChannel"] == "public_stable"
    assert result["releaseManifestChannelMatchesReleaseChannel"] is True
    assert result["expectedReleaseSupportabilityState"] == "gold_supported"
    assert result["releaseManifestSupportabilityState"] == "gold_supported"
    assert result["releaseManifestSupportabilityMatchesReleaseChannel"] is True
    assert result["expectedReleaseRolloutState"] == "public_stable"
    assert result["releaseManifestRolloutState"] == "public_stable"
    assert result["releaseManifestRolloutMatchesReleaseChannel"] is True
    assert result["preflightBlockingLockCount"] == 0
    assert result["preflightFindingCount"] == 0
    assert result["preflightStaleLookingLockCount"] == 0
    assert result["preflightStaleForeignLockCount"] == 0
    assert result["preflightStaleForeignLocksIgnored"] is False
    assert result["downloadsHasMarker"] is True
    assert result["statusRedirectHeading"] == "Stable downloads"
    assert result["statusRedirectHeadingRecognized"] is True
    assert result["statusRedirectHeadingExpected"] == "Stable downloads"
    assert result["statusRedirectHeadingMatchesReleaseChannel"] is True
    assert result["statusRedirectHeadingUsesGenericUpdatedCopy"] is False
    assert result["downloadsVersionMarkerValue"] == "Version run-20260630"
    assert result["statusRedirectVersionMarkerValue"] == "Version run-20260630"
    assert result["downloadsVersionMarkerMatchesReleaseChannel"] is True
    assert result["statusRedirectVersionMarkerMatchesReleaseChannel"] is True
    assert result["ledgerStreamNonCacheable"] is True
    assert result["ledgerStreamPrecached"] is False
    assert result["pwaRootWorkerKind"] == "play"
    assert result["pwaRootWorkerCacheVersion"] == "play-shell-v16"
    assert result["pwaFullDeploymentDigestSha256"] == "b" * 64
    assert result["pwaFullDeploymentDigestMatchesExpected"] is True
    assert result["expectedPwaFullDeploymentDigestSha256"] == "b" * 64
    assert result["rolePwaManifestCount"] == 2
    assert {
        (entry["role"], entry["id"], entry["start_url"])
        for entry in result["rolePwaManifests"]
    } == {
        ("Player", "/mobile/player", "/mobile/player"),
        ("GameMaster", "/mobile/gm", "/mobile/gm"),
    }
    assert result["mobileLedgerStatus"] == "pass"
    assert result["mobileLedgerPayloadStatus"] == "opt_in_required"
    assert result["mobileLedgerCacheControl"] == "private, no-store, no-cache, max-age=0"
    assert result["readyMobileHandoffStatus"] == "pass"
    assert "quick_rolls" in result["readyMobileHandoffToolIds"]
    assert "player" in result["readyMobileHandoffPacketRoles"]
    assert result["readyMobileHandoffFrontdoorLaunchRoute"] == "/mobile/player"
    assert {
        (entry["role"], entry["route"], entry["manifest_path"])
        for entry in result["readyMobileHandoffRoleRoutes"]
    } == {
        ("Player", "/mobile/player", "/manifest.player.webmanifest"),
        ("GameMaster", "/mobile/gm", "/manifest.gm.webmanifest"),
    }
    assert result["participateIframeShellStatus"] == "pass"
    assert result["participateIframeRouteCount"] == 2
    assert result["participateIframeRouteIframeCount"] == 2
    assert result["onlineLaunchStatus"] == "pass"
    assert result["onlineLaunchContract"] == "chummer.online_character_roster_launch.v1"
    assert result["onlineLaunchLaunchUrl"] == "https://chummer.run/app?command=character_roster"
    assert result["onlineLaunchFinalUrl"] == "https://chummer.run/blazor/app?command=character_roster"
    assert result["onlineLaunchHttpStatus"] == 200
    assert result["onlineLaunchHasBlazorMarker"] is True
    assert result["roleAliasRouteStatus"] == "pass"
    assert result["roleAliasRouteContract"] == "chummer.public_role_alias_routes.v1"
    assert result["roleAliasRouteDrift"] == []
    assert {
        (entry["aliasPath"], entry["finalRoute"], entry["expectedFinalRoute"])
        for entry in result["roleAliasRouteResults"]
    } == {
        ("/player", "/mobile/player", "/mobile/player"),
        ("/jammer", "/mobile/player", "/mobile/player"),
        ("/gm", "/mobile/gm", "/mobile/gm"),
        ("/observer", "/mobile/observer", "/mobile/observer"),
    }
    assert result["coreChildContracts"]["preflight"] == "chummer.public_edge_deploy_preflight.v1"
    assert result["coreChildContracts"]["downloads"] == "chummer.downloads_version_marker.v1"
    assert result["coreChildContracts"]["pwaStatic"] == "chummer.public_pwa_static_assets.v1"
    assert result["failures"] == []


def test_postdeploy_gate_accepts_real_live_pwa_receipt_shape_and_digest() -> None:
    module = load_module()
    (
        preflight,
        downloads,
        _legacy_pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
    ) = passing_receipts()
    pwa_static = {
        "contractName": "chummer.public_pwa_static_assets.v1",
        "assetContractName": "chummer.public_play_install_assets.v2",
        "status": "pass",
        "baseUrl": "https://chummer.run",
        "base_url": "https://chummer.run",
        "manifests": [
            {"path": "/manifest.play.webmanifest"},
            {"path": "/manifest.player.webmanifest"},
            {"path": "/manifest.gm.webmanifest"},
            {"path": "/manifest.observer.webmanifest"},
        ],
        "role_manifests": [
            {
                "role": "Player",
                "path": "/manifest.player.webmanifest",
                "id": "/mobile/player",
                "start_url": "/mobile/player",
                "display": "standalone",
            },
            {
                "role": "GameMaster",
                "path": "/manifest.gm.webmanifest",
                "id": "/mobile/gm",
                "start_url": "/mobile/gm",
                "display": "standalone",
            },
        ],
        "assets": [{"path": "/service-worker.js"}],
        "worker": {
            "cacheVersion": "v19",
            "cacheContract": "run-api-projection-v2",
        },
        "service_worker": {
            "worker_kind": "play",
            "cache_version": "v19",
            "ledger_stream_non_cacheable": True,
            "ledger_stream_precached": False,
        },
        "documents": [],
        "deploymentIdentity": {
            "ready": True,
            "code": "overlay_identity_bound",
            "sourceFingerprintSha256": "a" * 64,
            "fullDeploymentDigestSha256": "b" * 64,
            "matchesExpectedFullDeploymentDigest": True,
        },
    }

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
        role_alias_routes=passing_role_alias_routes(),
        online_launch=passing_online_launch_receipt(),
        expected_full_deployment_digest_sha256="b" * 64,
    )

    assert result["status"] == "pass", result["failures"]
    assert result["pwaFullDeploymentDigestSha256"] == "b" * 64
    assert result["pwaFullDeploymentDigestMatchesExpected"] is True
    assert not [
        failure for failure in result["failures"] if "public PWA static proof" in failure
    ]


def test_trusted_build_info_digest_rejects_coherent_self_assertion(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_module()
    source = {"aggregateSha256": "a" * 64}
    staged = {
        "algorithm": "sha256-canonical-path-content-size-posix-mode-runtime-mount-exclusions-v3",
        "aggregateSha256": "b" * 64,
        "fileCount": 1,
        "excludedRelativePaths": [
            "wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
        ],
    }
    overlay_root = tmp_path / "active" / "app"
    build_info_path = overlay_root / module.OVERLAY_BUILD_INFO_RELATIVE_PATH
    build_info_path.parent.mkdir(parents=True)
    payload = {
        "sourceFingerprint": source,
        "stagedPayloadFingerprint": staged,
        "payloadModeReceipt": {"contractName": "fixture"},
        "fullDeploymentDigest": module.full_deployment_digest(source, staged),
    }
    build_info_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(module, "source_fingerprint", lambda _root: source)
    monkeypatch.setattr(module, "staged_payload_fingerprint", lambda _root: staged)
    monkeypatch.setattr(
        module,
        "validate_payload_modes_against_receipt",
        lambda _root, _receipt: {"status": "pass"},
    )

    assert module.load_expected_full_deployment_digest(
        build_info_path,
        source_root=tmp_path,
        overlay_root=overlay_root,
    ) == payload["fullDeploymentDigest"]["sha256"]

    drifted_staged = {
        **staged,
        "excludedRelativePaths": [],
    }
    payload["stagedPayloadFingerprint"] = drifted_staged
    payload["fullDeploymentDigest"] = module.full_deployment_digest(
        source,
        drifted_staged,
    )
    build_info_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="full deployment digest is invalid"):
        module.load_expected_full_deployment_digest(
            build_info_path,
            source_root=tmp_path,
            overlay_root=overlay_root,
        )

    drifted_source = {"aggregateSha256": "c" * 64}
    payload["sourceFingerprint"] = drifted_source
    payload["stagedPayloadFingerprint"] = staged
    payload["fullDeploymentDigest"] = module.full_deployment_digest(
        drifted_source,
        staged,
    )
    build_info_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="full deployment digest is invalid"):
        module.load_expected_full_deployment_digest(
            build_info_path,
            source_root=tmp_path,
            overlay_root=overlay_root,
        )


@pytest.mark.parametrize(
    "raw_payload",
    [
        b'{"sourceFingerprint":{},"sourceFingerprint":{}}',
        b'{"value":NaN}',
        b'\xef\xbb\xbf{"value":1}',
    ],
    ids=["duplicate-key", "nan", "utf8-bom"],
)
def test_trusted_build_info_digest_rejects_non_strict_json(
    tmp_path: Path,
    raw_payload: bytes,
) -> None:
    module = load_module()
    overlay_root = tmp_path / "active" / "app"
    build_info_path = overlay_root / module.OVERLAY_BUILD_INFO_RELATIVE_PATH
    build_info_path.parent.mkdir(parents=True)
    build_info_path.write_bytes(raw_payload)

    with pytest.raises(RuntimeError, match="not strict UTF-8 JSON"):
        module.load_expected_full_deployment_digest(
            build_info_path,
            source_root=tmp_path,
            overlay_root=overlay_root,
        )


def test_trusted_build_info_digest_rejects_pathname_replacement_during_read(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_module()
    overlay_root = tmp_path / "active" / "app"
    build_info_path = overlay_root / module.OVERLAY_BUILD_INFO_RELATIVE_PATH
    build_info_path.parent.mkdir(parents=True)
    build_info_path.write_bytes(b'{"value":1}')
    replacement = build_info_path.with_name("replacement.json")
    replacement.write_bytes(b'{"value":1}')
    original_close = module.os.close
    replaced = False

    def replacing_close(descriptor: int) -> None:
        nonlocal replaced
        original_close(descriptor)
        if not replaced:
            replaced = True
            replacement.replace(build_info_path)

    monkeypatch.setattr(module.os, "close", replacing_close)

    with pytest.raises(RuntimeError, match="pathname changed after read"):
        module.load_expected_full_deployment_digest(
            build_info_path,
            source_root=tmp_path,
            overlay_root=overlay_root,
        )


def test_main_threads_preflight_deployment_digest_into_live_pwa_child(
    monkeypatch,
) -> None:
    module = load_module()
    receipts = passing_receipts()
    captured: dict[str, list[str]] = {}

    def fake_run_child(command, output, allow_failure):  # noqa: ANN001
        script = command[1]
        if script.endswith("check_public_edge_deploy_preflight.py"):
            return receipts[0]
        if script.endswith("verify_public_pwa_static_assets.py"):
            captured["pwa"] = command
            return receipts[2]
        return {}

    monkeypatch.setattr(module, "run_child", fake_run_child)
    monkeypatch.setattr(
        module,
        "compose_status",
        lambda *args, **kwargs: {"status": "pass", "failures": []},
    )
    monkeypatch.setattr(
        module,
        "probe_role_alias_routes",
        lambda base_url, timeout_seconds: passing_role_alias_routes(),
    )

    assert module.main(
        [
            "--base-url",
            "https://chummer.run",
            "--skip-release-version-match",
        ]
    ) == 0
    pwa_command = captured["pwa"]
    digest_index = pwa_command.index(
        "--expected-full-deployment-digest-sha256"
    )
    assert pwa_command[digest_index + 1] == "b" * 64
    inventory_index = pwa_command.index("--expected-asset-inventory-sha256")
    assert pwa_command[inventory_index + 1] == "c" * 64


def test_postdeploy_gate_accepts_online_launch_served_directly_on_app_path() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
        role_alias_routes=passing_role_alias_routes(),
        online_launch=passing_online_launch_direct_receipt(),
    )

    assert result["status"] == "pass"
    assert result["onlineLaunchFinalUrl"] == "https://chummer.run/app?command=character_roster"
    assert result["failures"] == []


def test_postdeploy_gate_fails_when_online_launch_route_is_empty_or_wrong() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    online_launch = passing_online_launch_receipt()
    online_launch["status"] = "fail"
    online_launch["final_url"] = "https://chummer.run/blazor/library"
    online_launch["has_blazor_marker"] = False

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        online_launch=online_launch,
    )

    assert result["status"] == "fail"
    assert result["onlineLaunchStatus"] == "fail"
    assert "Chummer Online launch proof is not pass" in result["failures"]
    assert "Chummer Online launch proof did not land on /app or /blazor/app" in result["failures"]
    assert "Chummer Online launch proof did not prove the Blazor shell" in result["failures"]


def test_postdeploy_gate_fails_when_public_role_aliases_drift() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    alias_routes = passing_role_alias_routes()
    alias_routes["status"] = "fail"
    alias_routes["results"][0].update(  # type: ignore[index, union-attr]
        {
            "finalUrl": "https://chummer.run/play?role=player",
            "finalRoute": "/play?role=player",
            "expectedFinalRoute": "/mobile/player",
            "pass": False,
        }
    )
    alias_routes["drift"] = [alias_routes["results"][0]]  # type: ignore[index]

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        role_alias_routes=alias_routes,
    )

    assert result["status"] == "fail"
    assert result["roleAliasRouteStatus"] == "fail"
    assert result["roleAliasRouteDrift"][0]["aliasPath"] == "/player"
    assert "role alias route redirects drifted" in result["failures"]
    assert "/player resolved to /play?role=player instead of /mobile/player" in result["failures"]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_first_hops",
        "missing_probe_query",
        "cross_origin_final",
        "raw_private_value",
    ],
)
def test_postdeploy_gate_revalidates_role_alias_receipt_evidence(mutation: str) -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    alias_routes = passing_role_alias_routes()
    jammer = next(
        row for row in alias_routes["results"]  # type: ignore[index, union-attr]
        if row["aliasPath"] == "/jammer"
    )
    if mutation == "missing_first_hops":
        jammer.pop("firstHopResults")
    elif mutation == "missing_probe_query":
        jammer["requestedUrl"] = "https://chummer.run/jammer"
    elif mutation == "cross_origin_final":
        jammer["finalUrl"] = "https://attacker.example/mobile/player#"
    else:
        jammer["requestedUrl"] = "https://chummer.run/jammer?sessionId=raw-private-value"

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        role_alias_routes=alias_routes,
    )

    assert result["status"] == "fail"
    assert "/jammer alias route proof does not satisfy the exact GET/HEAD private redirect contract" in result["failures"]
    serialized = json.dumps(result)
    assert "raw-private-value" not in serialized
    if mutation == "raw_private_value":
        assert "sessionId=[redacted]" in serialized


def test_postdeploy_gate_fails_when_core_child_contract_is_wrong() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["contractName"] = "chummer.downloads_version_marker.preview"

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["coreChildContracts"]["downloads"] == "chummer.downloads_version_marker.preview"
    assert "downloads child receipt contract is not chummer.downloads_version_marker.v1" in result["failures"]


def test_postdeploy_gate_fails_when_preflight_or_downloads_fail() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    preflight["status"] = "fail"
    preflight["activeLockCount"] = 3
    preflight["foreignLockCount"] = 2
    preflight["ignoredForeignLockCount"] = 0
    preflight["staleLookingLockCount"] = 2
    preflight["foreignLocksIgnored"] = False
    preflight["allowForeignBuildLocks"] = False
    preflight["staleForeignLockCount"] = 1
    preflight["findings"] = [
        {"id": "active_build_lane", "detail": "local source build"},
        {"id": "verification_error", "detail": "ps failed"},
    ]
    downloads["status"] = "fail"
    downloads["downloads_has_marker"] = False

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["preflightActiveLockCount"] == 3
    assert result["preflightBlockingLockCount"] == 1
    assert result["preflightForeignLockCount"] == 2
    assert result["preflightIgnoredForeignLockCount"] == 0
    assert result["preflightFindingCount"] == 2
    assert result["preflightForeignLocksIgnored"] is False
    assert result["preflightAllowForeignBuildLocks"] is False
    assert result["preflightStaleLookingLockCount"] == 2
    assert result["preflightStaleForeignLockCount"] == 1
    assert "public-edge deploy preflight is not pass" in result["failures"]
    assert "downloads version marker proof is not pass" in result["failures"]


def test_postdeploy_gate_surfaces_preflight_overlay_fingerprint_drift() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    preflight["status"] = "fail"
    preflight["findings"] = [
        {
            "id": "public_edge_overlay_source_fingerprint_mismatch",
            "detail": "overlay build info source fingerprint does not match current source: landing",
        }
    ]
    preflight["overlayBuildInfoSourceFingerprint"] = {
        "aggregateMatchesCurrentSource": False,
        "recordedAggregateSha256": "b" * 64,
        "expectedAggregateSha256": "a" * 64,
        "missingKeys": [],
        "mismatchedKeys": ["landing"],
    }

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource"] is False
    assert result["preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256"] == "b" * 64
    assert result["preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256"] == "a" * 64
    assert result["preflightOverlayBuildInfoSourceFingerprintMissingKeys"] == []
    assert result["preflightOverlayBuildInfoSourceFingerprintMismatchedKeys"] == ["landing"]
    assert "public-edge preflight overlay build info source fingerprint does not match current source: landing" in result["failures"]


def test_postdeploy_gate_fails_when_downloads_semantics_contradict_pass() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["downloads_has_marker"] = False
    downloads["status_redirect_has_marker"] = False
    downloads["visible_version"] = ""
    downloads["status_redirect_version"] = ""

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["downloadsStatus"] == "pass"
    assert "downloads receipt does not prove /downloads version marker" in result["failures"]
    assert "downloads receipt does not prove /status version marker" in result["failures"]
    assert "downloads receipt missing visible Version text" in result["failures"]
    assert "downloads receipt missing /status visible Version text" in result["failures"]


def test_postdeploy_gate_fails_when_status_redirect_heading_is_stale_generic_copy() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["status_redirect_heading"] = "Updated"
    downloads["status_redirect_heading_recognized"] = False
    downloads["status_redirect_heading_expected"] = "Stable downloads"
    downloads["status_redirect_heading_matches_release_channel"] = False
    downloads["status_redirect_heading_uses_generic_updated_copy"] = True

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["statusRedirectHeading"] == "Updated"
    assert "downloads receipt does not prove a recognized /status decision heading" in result["failures"]
    assert "downloads receipt still proves the stale generic Updated /status heading" in result["failures"]
    assert "downloads receipt does not prove the /status heading matches release posture" in result["failures"]


def test_postdeploy_gate_fails_when_downloads_marker_values_are_empty() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["status"] = "fail"
    downloads["failures"] = [
        "/downloads data-downloads-release-version is empty",
        "/status data-downloads-release-version is empty",
    ]
    downloads["downloads_version_marker_value"] = ""
    downloads["status_redirect_version_marker_value"] = ""
    downloads["downloads_version_marker_matches_release_channel"] = False
    downloads["status_redirect_version_marker_matches_release_channel"] = False
    downloads["visible_version_matches_release_channel"] = False
    downloads["status_redirect_version_matches_release_channel"] = False

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
    )

    assert result["status"] == "fail"
    assert result["downloadsStatus"] == "fail"
    assert result["downloadsVersionMarkerValue"] == ""
    assert result["statusRedirectVersionMarkerValue"] == ""
    assert result["visibleVersionMatchesReleaseChannel"] is False
    assert result["statusRedirectVersionMatchesReleaseChannel"] is False
    assert result["downloadsVersionMarkerMatchesReleaseChannel"] is False
    assert result["statusRedirectVersionMarkerMatchesReleaseChannel"] is False
    assert "downloads version marker proof is not pass" in result["failures"]
    assert "downloads receipt missing /downloads version marker value" in result["failures"]
    assert "downloads receipt missing /status version marker value" in result["failures"]
    assert "downloads version marker data does not match release channel" in result["failures"]
    assert "status redirect version marker data does not match release channel" in result["failures"]


def test_postdeploy_gate_fails_when_visible_version_mismatches_release_channel() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["visible_version"] = "Version 0.0.0.1"
    downloads["visible_version_matches_release_channel"] = False

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
    )

    assert result["status"] == "fail"
    assert result["expectedReleaseVersion"] == "run-20260630"
    assert result["visibleVersionMatchesReleaseChannel"] is False
    assert "downloads visible Version text does not match release channel" in result["failures"]


def test_postdeploy_gate_fails_when_status_redirect_version_mismatches_release_channel() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["status_redirect_version"] = "Version 0.0.0.1"
    downloads["status_redirect_version_matches_release_channel"] = False

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
    )

    assert result["status"] == "fail"
    assert result["expectedReleaseVersion"] == "run-20260630"
    assert result["visibleVersionMatchesReleaseChannel"] is True
    assert result["statusRedirectVersionMatchesReleaseChannel"] is False
    assert "status redirect visible Version text does not match release channel" in result["failures"]


def test_postdeploy_gate_fails_when_live_release_manifest_posture_mismatches_release_channel() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["release_manifest_status"] = "draft"
    downloads["release_manifest_status_matches_release_channel"] = False
    downloads["release_manifest_channel"] = "preview"
    downloads["release_manifest_channel_matches_release_channel"] = False
    downloads["release_manifest_supportability_state"] = "review_required"
    downloads["release_manifest_supportability_matches_release_channel"] = False
    downloads["release_manifest_rollout_state"] = "coverage_incomplete"
    downloads["release_manifest_rollout_matches_release_channel"] = False

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
    )

    assert result["status"] == "fail"
    assert result["releaseManifestStatus"] == "draft"
    assert result["releaseManifestChannel"] == "preview"
    assert result["releaseManifestSupportabilityState"] == "review_required"
    assert result["releaseManifestRolloutState"] == "coverage_incomplete"
    assert "downloads receipt live release manifest status does not match release channel" in result["failures"]
    assert "downloads receipt live release manifest channel does not match release channel" in result["failures"]
    assert "downloads receipt live release manifest supportability does not match release channel" in result["failures"]
    assert "downloads receipt live release manifest rollout does not match release channel" in result["failures"]


def test_postdeploy_gate_fails_when_expected_release_posture_is_not_launch_gold() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["expected_release_status"] = "draft"
    downloads["expected_release_channel"] = ""
    downloads["expected_release_supportability_state"] = "review_required"
    downloads["expected_release_rollout_state"] = "coverage_incomplete"
    downloads["release_manifest_status"] = "draft"
    downloads["release_manifest_status_matches_release_channel"] = True
    downloads["release_manifest_supportability_state"] = "review_required"
    downloads["release_manifest_rollout_state"] = "coverage_incomplete"
    downloads["release_manifest_supportability_matches_release_channel"] = True
    downloads["release_manifest_rollout_matches_release_channel"] = True

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
    )

    assert result["status"] == "fail"
    assert result["expectedReleaseStatus"] == "draft"
    assert result["expectedReleaseChannel"] == ""
    assert result["expectedReleaseSupportabilityState"] == "review_required"
    assert result["expectedReleaseRolloutState"] == "coverage_incomplete"
    assert "downloads receipt expected release status is not published" in result["failures"]
    assert "downloads receipt missing expected release channel" in result["failures"]
    assert "downloads receipt expected release rollout is blocking: coverage_incomplete" in result["failures"]


def test_postdeploy_gate_rejects_stable_channel_with_non_launch_supportability() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["expected_release_status"] = "published"
    downloads["expected_release_channel"] = "public_stable"
    downloads["expected_release_supportability_state"] = "preview_supported"
    downloads["expected_release_rollout_state"] = "public_stable"
    downloads["release_manifest_status"] = "published"
    downloads["release_manifest_status_matches_release_channel"] = True
    downloads["release_manifest_supportability_state"] = "preview_supported"
    downloads["release_manifest_supportability_matches_release_channel"] = True
    downloads["release_manifest_rollout_state"] = "public_stable"
    downloads["release_manifest_rollout_matches_release_channel"] = True

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
    )

    assert result["status"] == "fail"
    assert result["expectedReleaseChannel"] == "public_stable"
    assert result["expectedReleaseSupportabilityState"] == "preview_supported"
    assert "downloads receipt expected release supportability is not launch-supported" in result["failures"]


def test_postdeploy_gate_allows_review_required_stable_channel_when_launch_support_not_required() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["expected_release_status"] = "published"
    downloads["expected_release_channel"] = "public_stable"
    downloads["expected_release_supportability_state"] = "review_required"
    downloads["expected_release_rollout_state"] = "public_release_review_required"
    downloads["release_manifest_status"] = "published"
    downloads["release_manifest_status_matches_release_channel"] = True
    downloads["release_manifest_supportability_state"] = "review_required"
    downloads["release_manifest_supportability_matches_release_channel"] = True
    downloads["release_manifest_rollout_state"] = "public_release_review_required"
    downloads["release_manifest_rollout_matches_release_channel"] = True

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
        require_launch_supported_release_channel=False,
    )

    assert result["status"] == "pass"
    assert "downloads receipt expected release supportability is not launch-supported" not in result["failures"]


def test_postdeploy_gate_allows_coverage_incomplete_stable_channel_when_launch_support_not_required() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["expected_release_status"] = "published"
    downloads["expected_release_channel"] = "public_stable"
    downloads["expected_release_supportability_state"] = "review_required"
    downloads["expected_release_rollout_state"] = "coverage_incomplete"
    downloads["status_redirect_heading"] = "Preview downloads"
    downloads["status_redirect_heading_expected"] = "Preview downloads"
    downloads["status_redirect_heading_matches_release_channel"] = True
    downloads["visible_version"] = "Version 2026.06.30 (Preview)"
    downloads["status_redirect_version"] = "Version 2026.06.30 (Preview)"
    downloads["visible_version_matches_release_channel"] = True
    downloads["status_redirect_version_matches_release_channel"] = True
    downloads["release_manifest_status"] = "published"
    downloads["release_manifest_status_matches_release_channel"] = True
    downloads["release_manifest_supportability_state"] = "review_required"
    downloads["release_manifest_supportability_matches_release_channel"] = True
    downloads["release_manifest_rollout_state"] = "coverage_incomplete"
    downloads["release_manifest_rollout_matches_release_channel"] = True
    downloads["public_release_has_preview_or_review_caveat"] = True
    downloads["release_manifest_has_preview_or_review_caveat"] = True

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
        require_launch_supported_release_channel=False,
    )

    assert result["status"] == "pass"
    assert result["expectedReleaseRolloutState"] == "coverage_incomplete"
    assert "downloads receipt expected release rollout is blocking: coverage_incomplete" not in result["failures"]


def test_postdeploy_gate_fails_when_release_manifest_copy_is_unsafe() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["expected_release_channel"] = "preview"
    downloads["expected_release_supportability_state"] = "preview_supported"
    downloads["expected_release_rollout_state"] = "promoted_preview"
    downloads["release_manifest_channel"] = "preview"
    downloads["release_manifest_supportability_state"] = "preview_supported"
    downloads["release_manifest_rollout_state"] = "promoted_preview"
    downloads["public_release_copy_safe"] = False
    downloads["public_release_unsafe_copy_markers"] = ["checks are clear"]
    downloads["release_manifest_copy_safe"] = False
    downloads["release_manifest_unsafe_copy_markers"] = ["checks are clear"]

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
    )

    assert result["status"] == "fail"
    assert result["publicReleaseManifestCopySafe"] is False
    assert result["releaseManifestCopySafe"] is False
    assert "downloads receipt static public release manifest copy is not safe" in result["failures"]
    assert "downloads receipt live release manifest copy is not safe" in result["failures"]


def test_postdeploy_gate_fails_when_pwa_static_fails() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    pwa_static["status"] = "fail"

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert "public PWA static asset proof is not pass" in result["failures"]


def test_postdeploy_gate_fails_when_pwa_static_semantics_contradict_pass() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    pwa_static["manifests"] = [{}]
    pwa_static["role_manifests"] = []
    pwa_static["assets"] = []
    pwa_static["service_worker"] = {
        "worker_kind": "portal",
        "cache_name": "chummer-public-v4",
        "ledger_stream_non_cacheable": False,
        "ledger_stream_precached": True,
    }

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["pwaStaticStatus"] == "pass"
    assert result["pwaManifestCount"] == 1
    assert result["rolePwaManifestCount"] == 0
    assert result["pwaAssetCount"] == 0
    assert result["pwaRootWorkerKind"] == "portal"
    assert "public PWA static proof does not include all manifests" in result["failures"]
    assert "public PWA static proof does not include the Player role manifest" in result["failures"]
    assert "public PWA static proof does not include the GameMaster role manifest" in result["failures"]
    assert "public PWA static proof does not include required assets" in result["failures"]
    assert "public PWA static proof does not keep ledger stream non-cacheable" in result["failures"]
    assert "public PWA static proof precaches personalized ledger stream" in result["failures"]
    assert "public PWA static proof does not use the Play root service worker" in result["failures"]


def test_postdeploy_gate_fails_when_mobile_ledger_boundary_fails() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    mobile_ledger["status"] = "fail"

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["mobileLedgerStatus"] == "fail"
    assert "mobile PWA ledger boundary proof is not pass" in result["failures"]


def test_postdeploy_gate_fails_when_mobile_ledger_semantics_contradict_pass() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    mobile_ledger["payload_status"] = "live"
    mobile_ledger["cache_control"] = "public, max-age=3600"
    mobile_ledger["vary"] = "Accept-Encoding"

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["mobileLedgerStatus"] == "pass"
    assert result["mobileLedgerPayloadStatus"] == "live"
    assert "mobile ledger receipt payload is not opt_in_required" in result["failures"]
    assert "mobile ledger cache-control is missing private/no-store/no-cache/max-age=0" in result["failures"]
    assert "mobile ledger vary is missing Cookie and Authorization" in result["failures"]


def test_postdeploy_gate_fails_when_ready_mobile_handoff_fails() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    ready_mobile_handoff["status"] = "fail"

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["readyMobileHandoffStatus"] == "fail"
    assert "Ready mobile handoff proof is not pass" in result["failures"]


def test_postdeploy_gate_fails_when_ready_mobile_handoff_semantics_contradict_pass() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    ready_mobile_handoff["tool_ids"] = ["inventory", "health"]
    ready_mobile_handoff["packet_roles"] = ["player"]
    ready_mobile_handoff["frontdoor_launch_route"] = "/mobile"
    ready_mobile_handoff["role_routes"] = [
        {
            "role": "Player",
            "mode": "player",
            "route": "/mobile/player",
        }
    ]

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["readyMobileHandoffStatus"] == "pass"
    assert "Ready mobile handoff is missing required tools: ammo, living_world, modifiers, quick_rolls" in result["failures"]
    assert "Ready mobile handoff is missing required packet roles: gm, organizer" in result["failures"]
    assert "Ready mobile handoff frontdoor launch route is not /mobile/player" in result["failures"]
    assert "Ready mobile handoff Player manifest path is not /manifest.player.webmanifest" in result["failures"]
    assert "Ready mobile handoff is missing the GameMaster role route" in result["failures"]


def test_postdeploy_gate_fails_when_participate_iframe_shell_fails() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    participate_iframe_shell["status"] = "fail"
    participate_iframe_shell["route_count"] = 2
    participate_iframe_shell["iframe_route_count"] = 0

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["participateIframeShellStatus"] == "fail"
    assert result["participateIframeRouteCount"] == 2
    assert result["participateIframeRouteIframeCount"] == 0
    assert "Participate iframe shell proof is not pass" in result["failures"]


def test_postdeploy_gate_fails_when_participate_iframe_semantics_contradict_pass() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    participate_iframe_shell["route_count"] = 1
    participate_iframe_shell["iframe_route_count"] = 1
    participate_iframe_shell["offline_fallback_route_count"] = 1

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["participateIframeShellStatus"] == "pass"
    assert result["participateIframeRouteCount"] == 1
    assert result["participateIframeRouteOfflineFallbackCount"] == 1
    assert "Participate iframe shell route count is below required public routes" in result["failures"]
    assert "Participate iframe shell does not prove both iframe routes" in result["failures"]
    assert "Participate iframe shell is using offline fallback routes" in result["failures"]


def test_postdeploy_gate_can_require_downloads_status_browser_proof() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-downloads-status-browser",
            "artifact": {
                "contractName": "chummer.downloads_status_e2e.v1",
                "status_redirect_heading": "Stable downloads",
                "status_redirect_heading_recognized": True,
                "status_redirect_heading_expected": "Stable downloads",
                "status_redirect_heading_matches_release_channel": True,
                "status_redirect_heading_uses_generic_updated_copy": False,
            },
        },
    )

    assert result["status"] == "pass"
    assert result["downloadsStatusBrowserStatus"] == "pass"
    assert result["downloadsStatusBrowserArtifactContract"] == "chummer.downloads_status_e2e.v1"
    assert result["downloadsStatusBrowserStatusRedirectHeading"] == "Stable downloads"
    assert result["downloadsStatusBrowserStatusRedirectHeadingMatchesReleaseChannel"] is True

    failing = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        {
            "status": "fail",
            "exitCode": 1,
            "artifactDir": "/tmp/chummer-downloads-status-browser",
            "artifact": {
                "contractName": "chummer.downloads_status_e2e.v1",
                "status_redirect_heading": "Stable downloads",
                "status_redirect_heading_recognized": True,
                "status_redirect_heading_expected": "Stable downloads",
                "status_redirect_heading_matches_release_channel": True,
                "status_redirect_heading_uses_generic_updated_copy": False,
            },
        },
    )

    assert failing["status"] == "fail"
    assert failing["downloadsStatusBrowserStatus"] == "fail"
    assert failing["downloadsStatusBrowserExitCode"] == 1
    assert "downloads-status Playwright proof is not pass" in failing["failures"]


def test_postdeploy_gate_rejects_downloads_status_browser_proof_when_status_heading_semantics_drift() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-downloads-status-browser",
            "artifact": {
                "contractName": "chummer.downloads_status_e2e.v1",
                "status_redirect_heading": "Updated",
                "status_redirect_heading_recognized": False,
                "status_redirect_heading_expected": "Stable downloads",
                "status_redirect_heading_matches_release_channel": False,
                "status_redirect_heading_uses_generic_updated_copy": True,
            },
        },
    )

    assert result["status"] == "fail"
    assert result["downloadsStatusBrowserStatus"] == "pass"
    assert result["downloadsStatusBrowserStatusRedirectHeading"] == "Updated"
    assert result["downloadsStatusBrowserStatusRedirectHeadingRecognized"] is False
    assert result["downloadsStatusBrowserStatusRedirectHeadingMatchesReleaseChannel"] is False
    assert result["downloadsStatusBrowserStatusRedirectHeadingUsesGenericUpdatedCopy"] is True
    assert "downloads-status Playwright proof does not prove a recognized /status decision heading" in result["failures"]
    assert "downloads-status Playwright proof still uses stale generic Updated heading" in result["failures"]
    assert "downloads-status Playwright proof does not prove the /status heading matches release posture" in result["failures"]


def test_downloads_status_browser_timeout_returns_failed_receipt(monkeypatch, tmp_path) -> None:
    module = load_module()

    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["npx", "playwright"],
            timeout=120,
            output="partial stdout",
            stderr="partial stderr",
        )

    monkeypatch.setattr(module.subprocess, "run", timeout_run)

    result = module.run_downloads_status_playwright("https://chummer.run", tmp_path, 20)

    assert result["status"] == "fail"
    assert result["exitCode"] == 124
    assert result["timedOut"] is True
    assert result["timeoutSeconds"] == 120
    assert result["artifact"] == {}
    assert result["stdoutTail"] == "partial stdout"
    assert result["stderrTail"] == "partial stderr"


def test_downloads_status_browser_can_reuse_existing_artifact(monkeypatch, tmp_path) -> None:
    module = load_module()
    artifact_path = tmp_path / "DOWNLOADS_STATUS_E2E.generated.json"
    artifact_path.write_text(
        json.dumps(
            {
                "contractName": "chummer.downloads_status_e2e.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )

    def unexpected_run(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("Playwright should not run when a reusable artifact already exists.")

    monkeypatch.setattr(module, "run_playwright_command", unexpected_run)

    result = module.run_downloads_status_playwright(
        "https://chummer.run",
        tmp_path,
        20,
        reuse_existing_artifact=True,
    )

    assert result["status"] == "pass"
    assert result["exitCode"] == 0
    assert result["artifactReused"] is True
    assert result["playwrightExecuted"] is False
    assert result["artifactBaseUrlMatchesRequested"] is True
    assert result["artifactContract"] == "chummer.downloads_status_e2e.v1"
    assert result["artifactFresh"] is True


def test_postdeploy_gate_rejects_downloads_status_wrong_artifact_contract() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-downloads-status-browser",
            "artifact": {
                "contractName": "chummer.downloads_status_e2e.preview",
            },
        },
    )

    assert result["status"] == "fail"
    assert result["downloadsStatusBrowserArtifactContract"] == "chummer.downloads_status_e2e.preview"
    assert "downloads-status Playwright artifact contract is not chummer.downloads_status_e2e.v1" in result["failures"]


def test_downloads_status_browser_stale_artifact_reruns_playwright(monkeypatch, tmp_path) -> None:
    module = load_module()
    artifact_path = tmp_path / "DOWNLOADS_STATUS_E2E.generated.json"
    artifact_path.write_text(
        json.dumps(
            {
                "contractName": "chummer.downloads_status_e2e.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": (datetime.now(UTC) - timedelta(hours=48)).isoformat().replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )
    invoked: dict[str, object] = {}

    def fake_run(command, env, timeout_seconds):  # noqa: ANN001
        invoked["command"] = command
        invoked["env"] = env
        invoked["timeout_seconds"] = timeout_seconds
        artifact_path.write_text(
            json.dumps(
                {
                    "contractName": "chummer.downloads_status_e2e.v1",
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                }
            ),
            encoding="utf-8",
        )
        return 0, "fresh run", "", False

    monkeypatch.setattr(module, "run_playwright_command", fake_run)

    result = module.run_downloads_status_playwright(
        "https://chummer.run",
        tmp_path,
        20,
        reuse_existing_artifact=True,
    )

    assert result["status"] == "pass"
    assert result["artifactReused"] is False
    assert result["playwrightExecuted"] is True
    assert invoked["timeout_seconds"] == 120


def test_downloads_status_browser_malformed_reuse_artifact_reruns_playwright(monkeypatch, tmp_path) -> None:
    module = load_module()
    artifact_path = tmp_path / "DOWNLOADS_STATUS_E2E.generated.json"
    artifact_path.write_text("{not json", encoding="utf-8")
    invoked: dict[str, object] = {}

    def fake_run(command, env, timeout_seconds):  # noqa: ANN001
        invoked["command"] = command
        invoked["env"] = env
        invoked["timeout_seconds"] = timeout_seconds
        artifact_path.write_text(
            json.dumps(
                {
                    "contractName": "chummer.downloads_status_e2e.v1",
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                }
            ),
            encoding="utf-8",
        )
        return 0, "fresh run", "", False

    monkeypatch.setattr(module, "run_playwright_command", fake_run)

    result = module.run_downloads_status_playwright(
        "https://chummer.run",
        tmp_path,
        20,
        reuse_existing_artifact=True,
    )

    assert result["status"] == "pass"
    assert result["artifactReused"] is False
    assert result["playwrightExecuted"] is True
    assert result["artifactLoadStatus"] == "loaded"
    assert invoked["timeout_seconds"] == 120


def test_postdeploy_gate_can_require_mobile_pwa_viewport_browser_proof() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    mobile_routes = sorted(module.REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES)
    mobile_proof = passing_mobile_pwa_viewport_browser_proof(module)

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        mobile_proof,
    )

    assert result["status"] == "pass"
    assert result["mobilePwaViewportStatus"] == "pass"
    assert result["mobilePwaViewportArtifactContract"] == "chummer.mobile_pwa_viewport_smoke.v1"
    assert result["mobilePwaViewportRouteCount"] == 7
    assert result["mobilePwaViewportViewportCount"] == 3
    assert result["mobilePwaViewportRoutes"] == mobile_routes
    assert result["mobilePwaViewportMissingRoutes"] == []
    assert result["mobilePwaViewportArtifactCurrentContractSatisfied"] is True
    assert result["mobilePwaViewportArtifactContractFailures"] == []

    failing_proof = passing_mobile_pwa_viewport_browser_proof(module)
    failing_proof["status"] = "fail"
    failing_proof["exitCode"] = 1
    failing = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        failing_proof,
    )

    assert failing["status"] == "fail"
    assert failing["mobilePwaViewportStatus"] == "fail"
    assert "mobile PWA viewport Playwright proof is not pass" in failing["failures"]


def test_postdeploy_gate_rejects_mobile_pwa_viewport_missing_role_routes() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    mobile_proof = passing_mobile_pwa_viewport_browser_proof(module)
    artifact = mobile_proof["artifact"]
    assert isinstance(artifact, dict)
    artifact["routes"] = sorted(module.REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES - {"/mobile/gm"})
    artifact["route_count"] = len(artifact["routes"])
    artifact["results"] = [
        result
        for result in artifact["results"]
        if result["route"] != "/mobile/gm"
    ]

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        mobile_proof,
    )

    assert result["status"] == "fail"
    assert result["mobilePwaViewportMissingRoutes"] == ["/mobile/gm"]
    assert "mobile PWA viewport Playwright route count is below required mobile routes" in result["failures"]
    assert "mobile PWA viewport Playwright proof is missing required routes: /mobile/gm" in result["failures"]


def test_postdeploy_gate_rejects_legacy_v1_mobile_pwa_artifact_without_build_results() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    mobile_proof = passing_mobile_pwa_viewport_browser_proof(module)
    artifact = mobile_proof["artifact"]
    assert isinstance(artifact, dict)
    artifact["routes"] = [
        route for route in artifact["routes"] if route != "/build"
    ]
    artifact["route_count"] = len(artifact["routes"])
    artifact["results"] = [
        row for row in artifact["results"] if row["route"] != "/build"
    ]

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        mobile_proof,
    )

    assert result["status"] == "fail"
    assert result["mobilePwaViewportArtifactCurrentContractSatisfied"] is False
    assert result["mobilePwaViewportMissingRoutes"] == ["/build"]
    assert "mobile PWA viewport Playwright proof is missing required routes: /build" in result["failures"]
    assert any(
        "mobile PWA viewport Playwright proof is missing required results:"
        in failure
        and "/build@desktop-1366" in failure
        and "/build@phone-390" in failure
        and "/build@tablet" in failure
        for failure in result["failures"]
    )


@pytest.mark.parametrize(
    "field",
    sorted(
        {
            "route",
            "viewport",
            "width",
            "height",
            "status",
            "overflow_x",
            "navigation_error",
            "final_url",
            "build_layout_source",
            "build_layout_preference",
            "build_layout_effective",
            "build_layout_override_checked",
        }
    ),
)
def test_mobile_pwa_artifact_contract_rejects_each_required_build_result_field(
    field: str,
) -> None:
    module = load_module()
    artifact = passing_mobile_pwa_viewport_artifact(module)
    build_result = next(
        row
        for row in artifact["results"]
        if row["route"] == "/build" and row["viewport"] == "phone-390"
    )
    del build_result[field]

    assert not module.mobile_pwa_viewport_artifact_matches_current_contract(
        artifact,
        expected_base_url="https://chummer.run",
    )


@pytest.mark.parametrize(
    "drift",
    ["missing-build-results", "missing-build-field"],
)
def test_mobile_pwa_incomplete_reuse_artifact_reruns_canonical_playwright_path(
    monkeypatch,
    tmp_path: Path,
    drift: str,
) -> None:
    module = load_module()
    artifact_path = tmp_path / "MOBILE_PWA_VIEWPORT_SMOKE.generated.json"
    legacy_artifact = passing_mobile_pwa_viewport_artifact(module)
    if drift == "missing-build-results":
        legacy_artifact["routes"] = [
            route for route in legacy_artifact["routes"] if route != "/build"
        ]
        legacy_artifact["route_count"] = len(legacy_artifact["routes"])
        legacy_artifact["results"] = [
            row for row in legacy_artifact["results"] if row["route"] != "/build"
        ]
    else:
        build_result = next(
            row
            for row in legacy_artifact["results"]
            if row["route"] == "/build" and row["viewport"] == "desktop-1366"
        )
        del build_result["build_layout_effective"]
    artifact_path.write_text(json.dumps(legacy_artifact), encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run_playwright_command(command, env, timeout_seconds):  # noqa: ANN001
        captured["command"] = command
        captured["env"] = env
        captured["timeout_seconds"] = timeout_seconds
        captured["stale_artifact_removed"] = not artifact_path.exists()
        artifact_path.write_text(
            json.dumps(passing_mobile_pwa_viewport_artifact(module)),
            encoding="utf-8",
        )
        return 0, "fresh Build proof", "", False

    monkeypatch.setattr(
        module,
        "run_playwright_command",
        fake_run_playwright_command,
    )

    result = module.run_mobile_pwa_viewport_playwright(
        "https://chummer.run",
        tmp_path,
        20.0,
        reuse_existing_artifact=True,
    )

    assert result["status"] == "pass"
    assert result["artifactReused"] is False
    assert result["playwrightExecuted"] is True
    assert result["artifactCurrentContractSatisfied"] is True
    assert result["artifactContractFailures"] == []
    assert result["artifactPath"] == str(artifact_path)
    assert captured["stale_artifact_removed"] is True
    assert captured["timeout_seconds"] == 300
    assert captured["command"] == [
        "npx",
        "playwright",
        "test",
        "tests/public/mobile-pwa-viewport-smoke.spec.ts",
        "--workers=1",
        "--reporter=line",
    ]


def test_mobile_pwa_complete_build_artifact_is_reusable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_module()
    artifact_path = tmp_path / "MOBILE_PWA_VIEWPORT_SMOKE.generated.json"
    artifact_path.write_text(
        json.dumps(passing_mobile_pwa_viewport_artifact(module)),
        encoding="utf-8",
    )

    def unexpected_run(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("Playwright should not run for a complete Build-aware artifact")

    monkeypatch.setattr(module, "run_playwright_command", unexpected_run)

    result = module.run_mobile_pwa_viewport_playwright(
        "https://chummer.run",
        tmp_path,
        20.0,
        reuse_existing_artifact=True,
    )

    assert result["status"] == "pass"
    assert result["artifactReused"] is True
    assert result["playwrightExecuted"] is False
    assert result["artifactCurrentContractSatisfied"] is True
    assert result["artifactContractFailures"] == []


def test_postdeploy_gate_can_require_pwa_offline_cache_browser_proof() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        None,
        passing_pwa_offline_browser_proof(),
    )

    assert result["status"] == "pass"
    assert result["pwaOfflineCacheStatus"] == "pass"
    assert result["pwaOfflineCacheArtifactContract"] == "chummer.pwa_offline_cache.v2"
    assert result["pwaOfflineCacheCacheVersion"] == "v17"
    assert result["pwaOfflineCacheNavigationPolicy"] == "network_only"
    assert result["pwaOfflineCachePrivateStateScope"] == "open_tab_only"
    assert "/mobile.css" in result["pwaOfflineCacheStaticPaths"]
    assert "/mobile/player" not in result["pwaOfflineCacheStaticPaths"]
    assert result["pwaOfflineCachePrivateNavigationCached"] is False
    assert result["pwaOfflineCachePrivateApiCached"] is False
    assert result["pwaOfflineCacheQueryBearingRequestsCached"] is False
    assert result["pwaOfflineCachePersonalizedLedgerCached"] is False
    assert {item["role"] for item in result["pwaOfflineCacheOfflineRoleFallbacks"]} == {"Player", "GameMaster"}

    failing = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-pwa-offline-cache",
            "artifact": {
                "contractName": "chummer.pwa_offline_cache.v1",
                "status": "pass",
                "offline_reload": "pass",
                "cached_paths": ["/mobile/player", "/mobile/gm"],
                "offline_role_routes": [],
                "personalized_ledger_cached": True,
            },
        },
    )

    assert failing["status"] == "fail"
    assert "PWA offline cache Playwright artifact contract is not chummer.pwa_offline_cache.v2" in failing["failures"]
    assert "PWA offline cache proof did not cache /manifest.player.webmanifest" in failing["failures"]
    assert "PWA offline cache proof navigation policy is not network_only" in failing["failures"]
    assert "PWA offline cache proof cached private role navigation" in failing["failures"]
    assert "PWA offline cache proof cached the personalized ledger stream" in failing["failures"]
    assert "PWA offline cache proof is missing Player fail-closed role fallback" in failing["failures"]
    assert "PWA offline cache proof is missing GameMaster fail-closed role fallback" in failing["failures"]


def test_pwa_offline_cache_v1_private_navigation_receipt_is_not_reused(monkeypatch, tmp_path) -> None:
    module = load_module()
    artifact_path = tmp_path / "PWA_OFFLINE_CACHE.generated.json"
    artifact_path.write_text(
        json.dumps(
            {
                "contractName": "chummer.pwa_offline_cache.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "cached_paths": ["/mobile/player", "/mobile/gm"],
                "offline_role_routes": ["player", "gm"],
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_run_playwright_command(command, env, timeout_seconds):  # noqa: ANN001
        captured["command"] = command
        artifact = dict(passing_pwa_offline_browser_proof()["artifact"])  # type: ignore[arg-type]
        artifact["base_url"] = "https://chummer.run"
        artifact["generated_at_utc"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        return 0, "", "", False

    monkeypatch.setattr(module, "run_playwright_command", fake_run_playwright_command)

    result = module.run_pwa_offline_cache_playwright(
        "https://chummer.run",
        tmp_path,
        20.0,
        reuse_existing_artifact=True,
    )

    assert "command" in captured
    assert result["status"] == "pass"
    assert result["artifactReused"] is False
    assert result["playwrightExecuted"] is True
    assert result["artifactContract"] == "chummer.pwa_offline_cache.v2"
    assert result["artifactPrivacyContractSatisfied"] is True


def test_postdeploy_gate_accepts_nested_blazor_new_runner_browser_proof() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        None,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-blazor-new-runner-menu",
            "artifact": {
                "contractName": "chummer.blazor_new_runner_menu.v1",
                "app_route": {
                    "initial_url": "https://chummer.run/blazor/app?command=new_character",
                    "file_menu_locked_during_dialog": True,
                },
                "app_roster_transition": {
                    "initial_url": "https://chummer.run/blazor/app",
                    "resolved_new_runner_href": "app?command=new_character",
                    "final_url": "https://chummer.run/blazor/app?command=new_character",
                    "active_workflow": "build-lab",
                    "command": "new-character",
                    "startup_command": "new_character",
                    "dialog_count": 1,
                    "headline": "New runner",
                    "workflow_heading": "Build Lab shell",
                    "file_menu_locked_during_dialog": True,
                    "new_tool_locked_during_dialog": True,
                },
                "workbench_fallback_route": {
                    "resolved_new_runner_href": "workbench?workspace=blue-workspace&tab=tab-create&command=new_character",
                    "final_url": "https://chummer.run/blazor/workbench?workspace=blue-workspace&tab=tab-create&command=new_character",
                    "reopened_data_command": "new_character",
                    "reopened_data_tab": "tab-create",
                    "dialog_count": 1,
                    "dialog_title": "New runner",
                },
            },
        },
    )

    assert result["status"] == "pass"
    assert result["blazorNewRunnerMenuStatus"] == "pass"
    assert result["blazorNewRunnerMenuArtifactContract"] == "chummer.blazor_new_runner_menu.v1"
    assert result["blazorNewRunnerMenuAppResolvedHref"] == "app?command=new_character"
    assert result["blazorNewRunnerMenuAppFinalUrl"] == "https://chummer.run/blazor/app?command=new_character"
    assert result["blazorNewRunnerMenuAppActiveWorkflow"] == "build-lab"
    assert result["blazorNewRunnerMenuAppCommand"] == "new-character"
    assert result["blazorNewRunnerMenuAppStartupCommand"] == "new_character"
    assert result["blazorNewRunnerMenuAppDialogCount"] == 1
    assert result["blazorNewRunnerMenuAppHeadline"] == "New runner"
    assert result["blazorNewRunnerMenuAppWorkflowHeading"] == "Build Lab shell"
    assert result["blazorNewRunnerMenuAppFileMenuLockedDuringDialog"] is True
    assert result["blazorNewRunnerMenuAppNewToolLockedDuringDialog"] is True
    assert result["blazorNewRunnerMenuResolvedHref"] == "workbench?workspace=blue-workspace&tab=tab-create&command=new_character"
    assert result["blazorNewRunnerMenuFinalUrl"] == "https://chummer.run/blazor/workbench?workspace=blue-workspace&tab=tab-create&command=new_character"
    assert result["blazorNewRunnerMenuReopenedDataCommand"] == "new_character"
    assert result["blazorNewRunnerMenuReopenedDataTab"] == "tab-create"
    assert result["blazorNewRunnerMenuDialogCount"] == 1
    assert result["blazorNewRunnerMenuDialogTitle"] == "New runner"


def test_postdeploy_gate_rejects_blazor_new_runner_browser_proof_when_app_roster_transition_drifts() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        None,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-blazor-new-runner-menu",
            "artifact": {
                "contractName": "chummer.blazor_new_runner_menu.v1",
                "app_roster_transition": {
                    "initial_url": "https://chummer.run/blazor/app",
                    "resolved_new_runner_href": "app?command=new_character",
                    "final_url": "https://chummer.run/blazor/app?command=new_character",
                    "active_workflow": "dossier",
                    "command": "none",
                    "startup_command": "none",
                    "dialog_count": 0,
                    "headline": "Character Roster",
                    "workflow_heading": "Roster shell",
                    "file_menu_locked_during_dialog": False,
                    "new_tool_locked_during_dialog": False,
                },
                "workbench_fallback_route": {
                    "resolved_new_runner_href": "workbench?workspace=blue-workspace&tab=tab-create&command=new_character",
                    "final_url": "https://chummer.run/blazor/workbench?workspace=blue-workspace&tab=tab-create&command=new_character",
                    "reopened_data_command": "new_character",
                    "reopened_data_tab": "tab-create",
                    "dialog_count": 1,
                    "dialog_title": "New runner",
                },
            },
        },
    )

    assert result["status"] == "fail"
    assert "Blazor new-runner Playwright proof did not transition app roster into the Build Lab workflow" in result["failures"]
    assert "Blazor new-runner Playwright proof did not switch app roster to command=new-character" in result["failures"]
    assert "Blazor new-runner Playwright proof did not preserve startup command new_character on app roster transition" in result["failures"]
    assert "Blazor new-runner Playwright proof did not reopen exactly one startup dialog on the app roster route" in result["failures"]


def test_postdeploy_gate_rejects_mobile_pwa_viewport_wrong_artifact_contract() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    mobile_proof = passing_mobile_pwa_viewport_browser_proof(module)
    artifact = mobile_proof["artifact"]
    assert isinstance(artifact, dict)
    artifact["contractName"] = "chummer.mobile_pwa_viewport_smoke.preview"

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        mobile_proof,
    )

    assert result["status"] == "fail"
    assert result["mobilePwaViewportArtifactContract"] == "chummer.mobile_pwa_viewport_smoke.preview"
    assert "mobile PWA viewport Playwright artifact contract is not chummer.mobile_pwa_viewport_smoke.v1" in result["failures"]


def test_postdeploy_gate_can_require_frontdoor_navigation_browser_proof() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-frontdoor-navigation",
            "mobileArtifact": {
                "contractName": "chummer.frontdoor_mobile_launch.v1",
                "gated_targets": ["Build", "Play"],
                "public_targets": [],
                "homepage_lane_text": "Current public lane: Stable.",
                "play_route": "/mobile/player",
                "play_sign_in_route": "/login?next=%2Fmobile%2Fplayer",
                "direct_player_route": "/mobile/player",
                "direct_player_http_status": 200,
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player",
                "live_turn_companion_shell": True,
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "rybbit_configured": True,
                "rybbit_tag": "mobile_play_shell",
                "rybbit_route": "/mobile/player",
                "rybbit_mode": "player",
                "rybbit_role": "Player",
                "rybbit_site_id_present": True,
                "rybbit_script_url_present": True,
                "rybbit_script_url_allowed": True,
                "rybbit_skip_patterns": ["/mobile/**"],
                "rybbit_mask_patterns": ["/api/play/**", "/mobile/**"],
                "rybbit_skip_mobile_paths": True,
                "rybbit_mask_mobile_paths": True,
                "rybbit_masks_private_play_routes": True,
                "rybbit_replay_block_selector": "[data-turn-root]",
                "rybbit_replay_blocks_turn_root": True,
                "player_session_handoff_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player",
                "player_session_handoff_status": "Session handoff is ready in the link above.",
                "player_session_handoff_link_text": "Open session handoff link",
                "player_session_handoff_preserves_session": True,
                "player_session_handoff_preserves_role": True,
                "player_session_handoff_strips_device": True,
                "player_session_handoff_sender_device_id_present": True,
                "gm_route": "/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_http_status": 200,
                "gm_final_url": "https://chummer.run/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_live_turn_companion_shell": True,
                "gm_pwa_manifest_path": "/manifest.gm.webmanifest",
                "gm_pwa_role": "GameMaster",
                "gm_blazor_shell": "interactive-server",
                "gm_rybbit_configured": True,
                "gm_rybbit_tag": "mobile_play_shell",
                "gm_rybbit_route": "/mobile/gm",
                "gm_rybbit_mode": "gm",
                "gm_rybbit_role": "GameMaster",
                "gm_rybbit_site_id_present": True,
                "gm_rybbit_script_url_present": True,
                "gm_rybbit_script_url_allowed": True,
                "gm_rybbit_skip_patterns": ["/mobile/**"],
                "gm_rybbit_mask_patterns": ["/api/play/**", "/mobile/**"],
                "gm_rybbit_skip_mobile_paths": True,
                "gm_rybbit_mask_mobile_paths": True,
                "gm_rybbit_masks_private_play_routes": True,
                "gm_rybbit_replay_block_selector": "[data-turn-root]",
                "gm_rybbit_replay_blocks_turn_root": True,
                "gm_session_handoff_url": "https://chummer.run/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_session_handoff_status": "Session handoff is ready in the link above.",
                "gm_session_handoff_link_text": "Open session handoff link",
                "gm_session_handoff_preserves_session": True,
                "gm_session_handoff_preserves_role": True,
                "gm_session_handoff_strips_device": True,
                "gm_session_handoff_sender_device_id_present": True,
            },
            "ledgerArtifact": {
                "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                "ledger_primary": False,
            },
            "anchorArtifact": {
                "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                "entry_url": "https://chummer.run/#turn-runsite-card",
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&deviceId=device-player-main&role=Player#turn-runsite-card",
                "final_pathname": "/mobile/player",
                "final_hash": "#turn-runsite-card",
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "session_id_present": True,
                "device_id_present": True,
                "failure": "",
            },
        },
    )

    # The legacy inline receipt above remains a regression input: v2 must reject it.
    assert result["status"] == "fail"
    assert "front-door navigation mobile artifact contains raw private session or device identity" in result["failures"]
    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        passing_frontdoor_navigation(),
    )

    assert result["status"] == "pass"
    assert result["frontdoorNavigationStatus"] == "pass"
    assert result["frontdoorNavigationMobileArtifactContract"] == "chummer.frontdoor_mobile_launch.v2"
    assert result["frontdoorNavigationLedgerArtifactContract"] == "chummer.black_ledger_globe_frontdoor.v1"
    assert result["frontdoorNavigationAnchorArtifactContract"] == "chummer.frontdoor_mobile_anchor_redirect.v2"
    assert result["frontdoorNavigationGatedTargets"] == ["Build", "Play"]
    assert result["frontdoorNavigationPublicTargets"] == []
    assert result["frontdoorNavigationHomepageLaneText"] == "Current public lane: Stable."
    assert result["frontdoorNavigationHomepageLaneExpected"] == "Current public lane: Stable."
    assert result["frontdoorNavigationHomepageLaneMatchesReleaseChannel"] is True
    assert result["frontdoorNavigationPlayRoute"] == "/mobile/player"
    assert result["frontdoorNavigationPlaySignInRoute"] == "/login?next=%2Fmobile%2Fplayer"
    assert result["frontdoorNavigationDirectPlayerRoute"] == "/mobile/player"
    assert result["frontdoorNavigationDirectPlayerHttpStatus"] == 200
    assert result["frontdoorNavigationFinalUrl"] == "https://chummer.run/mobile/player"
    assert result["frontdoorNavigationPrivateIdentityRedacted"] is True
    assert result["frontdoorNavigationVisiblePlayerUrlPrivateIdentityAbsent"] is True
    assert result["frontdoorNavigationPlayerSessionContextPresent"] is True
    assert result["frontdoorNavigationPlayerDeviceContextPresent"] is True
    assert result["frontdoorNavigationLiveTurnCompanionShell"] is True
    assert result["frontdoorNavigationPwaManifestPath"] == "/manifest.player.webmanifest"
    assert result["frontdoorNavigationPwaRole"] == "Player"
    assert result["frontdoorNavigationBlazorShell"] == "interactive-server"
    assert result["frontdoorNavigationRybbitConfigured"] is True
    assert result["frontdoorNavigationRybbitTag"] == "mobile_play_shell"
    assert result["frontdoorNavigationRybbitRoute"] == "/mobile/player"
    assert result["frontdoorNavigationRybbitMode"] == "player"
    assert result["frontdoorNavigationRybbitRole"] == "Player"
    assert result["frontdoorNavigationRybbitSiteIdPresent"] is True
    assert result["frontdoorNavigationRybbitScriptUrlPresent"] is True
    assert result["frontdoorNavigationRybbitScriptUrlAllowed"] is True
    assert result["frontdoorNavigationRybbitSkipPatterns"] == ["/mobile/**"]
    assert result["frontdoorNavigationRybbitMaskPatterns"] == ["/api/play/**", "/mobile/**"]
    assert result["frontdoorNavigationRybbitSkipMobilePaths"] is True
    assert result["frontdoorNavigationRybbitMaskMobilePaths"] is True
    assert result["frontdoorNavigationRybbitMasksPrivatePlayRoutes"] is True
    assert result["frontdoorNavigationRybbitReplayBlockSelector"] == "[data-turn-root]"
    assert result["frontdoorNavigationRybbitReplayBlocksTurnRoot"] is True
    assert result["frontdoorNavigationPlayerSessionHandoffUrl"] == "https://chummer.run/mobile/player?sessionId=[redacted]&role=Player"
    assert result["frontdoorNavigationPlayerSessionHandoffStatus"] == "Session handoff is ready in the link above."
    assert result["frontdoorNavigationPlayerSessionHandoffLinkText"] == "Open session handoff link"
    assert result["frontdoorNavigationPlayerSessionHandoffPreservesSession"] is True
    assert result["frontdoorNavigationPlayerSessionHandoffPreservesRole"] is True
    assert result["frontdoorNavigationPlayerSessionHandoffStripsDevice"] is True
    assert result["frontdoorNavigationPlayerSessionHandoffSenderDeviceIdPresent"] is True
    assert result["frontdoorNavigationPlayerSessionHandoffPrivateIdentityRedacted"] is True
    assert result["frontdoorNavigationGmRoute"] == "/mobile/gm"
    assert result["frontdoorNavigationGmRouteSessionIdPresent"] is True
    assert result["frontdoorNavigationGmRoutePrivateIdentityRedacted"] is True
    assert result["frontdoorNavigationGmHttpStatus"] == 200
    assert result["frontdoorNavigationGmFinalUrl"] == "https://chummer.run/mobile/gm"
    assert result["frontdoorNavigationVisibleGmUrlPrivateIdentityAbsent"] is True
    assert result["frontdoorNavigationGmSessionContextPresent"] is True
    assert result["frontdoorNavigationGmDeviceContextPresent"] is True
    assert result["frontdoorNavigationGmLiveTurnCompanionShell"] is True
    assert result["frontdoorNavigationGmPwaManifestPath"] == "/manifest.gm.webmanifest"
    assert result["frontdoorNavigationGmPwaRole"] == "GameMaster"
    assert result["frontdoorNavigationGmBlazorShell"] == "interactive-server"
    assert result["frontdoorNavigationGmRybbitConfigured"] is True
    assert result["frontdoorNavigationGmRybbitTag"] == "mobile_play_shell"
    assert result["frontdoorNavigationGmRybbitRoute"] == "/mobile/gm"
    assert result["frontdoorNavigationGmRybbitMode"] == "gm"
    assert result["frontdoorNavigationGmRybbitRole"] == "GameMaster"
    assert result["frontdoorNavigationGmRybbitSiteIdPresent"] is True
    assert result["frontdoorNavigationGmRybbitScriptUrlPresent"] is True
    assert result["frontdoorNavigationGmRybbitScriptUrlAllowed"] is True
    assert result["frontdoorNavigationGmRybbitSkipPatterns"] == ["/mobile/**"]
    assert result["frontdoorNavigationGmRybbitMaskPatterns"] == ["/api/play/**", "/mobile/**"]
    assert result["frontdoorNavigationGmRybbitSkipMobilePaths"] is True
    assert result["frontdoorNavigationGmRybbitMaskMobilePaths"] is True
    assert result["frontdoorNavigationGmRybbitMasksPrivatePlayRoutes"] is True
    assert result["frontdoorNavigationGmRybbitReplayBlockSelector"] == "[data-turn-root]"
    assert result["frontdoorNavigationGmRybbitReplayBlocksTurnRoot"] is True
    assert result["frontdoorNavigationGmSessionHandoffUrl"] == "https://chummer.run/mobile/gm?sessionId=[redacted]&role=GameMaster"
    assert result["frontdoorNavigationGmSessionHandoffStatus"] == "Session handoff is ready in the link above."
    assert result["frontdoorNavigationGmSessionHandoffLinkText"] == "Open session handoff link"
    assert result["frontdoorNavigationGmSessionHandoffPreservesSession"] is True
    assert result["frontdoorNavigationGmSessionHandoffPreservesRole"] is True
    assert result["frontdoorNavigationGmSessionHandoffStripsDevice"] is True
    assert result["frontdoorNavigationGmSessionHandoffSenderDeviceIdPresent"] is True
    assert result["frontdoorNavigationGmSessionHandoffPrivateIdentityRedacted"] is True
    assert result["frontdoorNavigationLedgerPrimary"] is False
    assert result["frontdoorNavigationAnchorEntryUrl"] == "https://chummer.run/#turn-runsite-card"
    assert result["frontdoorNavigationAnchorFinalPath"] == "/mobile/player"
    assert result["frontdoorNavigationAnchorFinalHash"] == "#turn-runsite-card"
    assert result["frontdoorNavigationAnchorPwaManifestPath"] == "/manifest.player.webmanifest"
    assert result["frontdoorNavigationAnchorPwaRole"] == "Player"
    assert result["frontdoorNavigationAnchorBlazorShell"] == "interactive-server"
    assert result["frontdoorNavigationAnchorPrivateIdentityRedacted"] is True
    assert result["frontdoorNavigationAnchorVisibleUrlPrivateIdentityAbsent"] is True
    assert result["frontdoorNavigationAnchorSessionContextPresent"] is True
    assert result["frontdoorNavigationAnchorDeviceContextPresent"] is True
    assert result["frontdoorNavigationAnchorFailure"] == ""
    assert result["frontdoorNavigationAnchorArtifactCurrentContractSatisfied"] is True

    failing = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        {
            "status": "fail",
            "exitCode": 1,
            "artifactDir": "/tmp/chummer-frontdoor-navigation",
            "mobileArtifact": {},
            "ledgerArtifact": {},
            "anchorArtifact": {},
        },
    )

    assert failing["status"] == "fail"
    assert failing["frontdoorNavigationStatus"] == "fail"
    assert "front-door navigation Playwright proof is not pass" in failing["failures"]
    assert failing["frontdoorNavigationAnchorFailure"] is None


def test_expected_homepage_lane_text_allows_blank_status_for_gold_supported_stable_lane() -> None:
    module = load_module()

    assert module.expected_homepage_lane_text(
        "",
        "run-20260630",
        "public_stable",
        "gold_supported",
        "public_stable",
    ) == "Current public lane: Stable."


def test_postdeploy_gate_surfaces_frontdoor_anchor_failure_detail() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    failing = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        {
            "status": "fail",
            "exitCode": 1,
            "artifactDir": "/tmp/chummer-frontdoor-navigation",
            "mobileArtifact": {},
            "ledgerArtifact": {},
            "anchorArtifact": {
                "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                "entry_url": "https://chummer.run/#turn-runsite-card?",
                "final_url": "https://chummer.run/#turn-runsite-card",
                "final_pathname": "/",
                "final_hash": "#turn-runsite-card",
                "pwa_manifest_path": "/manifest.json",
                "pwa_role": None,
                "blazor_shell": None,
                "session_id_present": False,
                "device_id_present": False,
                "failure": "page.waitForURL: Timeout 60000ms exceeded.",
            },
        },
    )

    assert failing["frontdoorNavigationAnchorFailure"] == "page.waitForURL: Timeout 60000ms exceeded."
    assert "front-door navigation homepage anchor proof failed: page.waitForURL: Timeout 60000ms exceeded." in failing["failures"]


def test_postdeploy_gate_accepts_canonical_frontdoor_anchor_entry_url() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-frontdoor-navigation",
            "mobileArtifact": {
                "contractName": "chummer.frontdoor_mobile_launch.v1",
                "gated_targets": ["Build", "Play"],
                "public_targets": [],
                "homepage_lane_text": "Current public lane: Stable.",
                "play_route": "/mobile/player",
                "play_sign_in_route": "/login?next=%2Fmobile%2Fplayer",
                "direct_player_http_status": 200,
                "direct_player_route": "/mobile/player",
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player",
                "live_turn_companion_shell": True,
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "rybbit_configured": True,
                "rybbit_tag": "mobile_play_shell",
                "rybbit_route": "/mobile/player",
                "rybbit_mode": "player",
                "rybbit_role": "Player",
                "rybbit_site_id_present": True,
                "rybbit_script_url_present": True,
                "rybbit_script_url_allowed": True,
                "rybbit_skip_patterns": ["/mobile/**"],
                "rybbit_mask_patterns": ["/api/play/**", "/mobile/**"],
                "rybbit_skip_mobile_paths": True,
                "rybbit_mask_mobile_paths": True,
                "rybbit_masks_private_play_routes": True,
                "rybbit_replay_block_selector": "[data-turn-root]",
                "rybbit_replay_blocks_turn_root": True,
                "player_session_handoff_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player",
                "player_session_handoff_status": "Session handoff is ready in the link above.",
                "player_session_handoff_link_text": "Open session handoff link",
                "player_session_handoff_preserves_session": True,
                "player_session_handoff_preserves_role": True,
                "player_session_handoff_strips_device": True,
                "player_session_handoff_sender_device_id_present": True,
                "gm_route": "/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_http_status": 200,
                "gm_final_url": "https://chummer.run/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_live_turn_companion_shell": True,
                "gm_pwa_manifest_path": "/manifest.gm.webmanifest",
                "gm_pwa_role": "GameMaster",
                "gm_blazor_shell": "interactive-server",
                "gm_rybbit_configured": True,
                "gm_rybbit_tag": "mobile_play_shell",
                "gm_rybbit_route": "/mobile/gm",
                "gm_rybbit_mode": "gm",
                "gm_rybbit_role": "GameMaster",
                "gm_rybbit_site_id_present": True,
                "gm_rybbit_script_url_present": True,
                "gm_rybbit_script_url_allowed": True,
                "gm_rybbit_skip_patterns": ["/mobile/**"],
                "gm_rybbit_mask_patterns": ["/api/play/**", "/mobile/**"],
                "gm_rybbit_skip_mobile_paths": True,
                "gm_rybbit_mask_mobile_paths": True,
                "gm_rybbit_masks_private_play_routes": True,
                "gm_rybbit_replay_block_selector": "[data-turn-root]",
                "gm_rybbit_replay_blocks_turn_root": True,
                "gm_session_handoff_url": "https://chummer.run/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_session_handoff_status": "Session handoff is ready in the link above.",
                "gm_session_handoff_link_text": "Open session handoff link",
                "gm_session_handoff_preserves_session": True,
                "gm_session_handoff_preserves_role": True,
                "gm_session_handoff_strips_device": True,
                "gm_session_handoff_sender_device_id_present": True,
            },
            "ledgerArtifact": {
                "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                "ledger_primary": False,
            },
            "anchorArtifact": {
                "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                "entry_url": "https://chummer.run/#turn-runsite-card",
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&deviceId=device-player-main&role=Player#turn-runsite-card",
                "final_pathname": "/mobile/player",
                "final_hash": "#turn-runsite-card",
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "session_id_present": True,
                "device_id_present": True,
                "failure": "",
            },
        },
    )

    assert result["status"] == "fail"
    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        passing_frontdoor_navigation(),
    )
    assert result["status"] == "pass"
    assert result["frontdoorNavigationAnchorEntryUrl"] == "https://chummer.run/#turn-runsite-card"
    assert "front-door navigation homepage anchor proof did not start from /#turn-runsite-card" not in result["failures"]


def test_postdeploy_gate_rejects_frontdoor_navigation_when_homepage_lane_disclosure_is_missing() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-frontdoor-navigation",
            "mobileArtifact": {
                "contractName": "chummer.frontdoor_mobile_launch.v1",
                "gated_targets": ["Build", "Play"],
                "public_targets": [],
                "homepage_lane_text": "",
                "play_route": "/mobile/player",
                "play_sign_in_route": "/login?next=%2Fmobile%2Fplayer",
                "direct_player_route": "/mobile/player",
                "direct_player_http_status": 200,
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player",
                "live_turn_companion_shell": True,
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "rybbit_configured": True,
                "rybbit_tag": "mobile_play_shell",
                "rybbit_route": "/mobile/player",
                "rybbit_mode": "player",
                "rybbit_role": "Player",
                "rybbit_site_id_present": True,
                "rybbit_script_url_present": True,
                "rybbit_script_url_allowed": True,
                "rybbit_skip_patterns": ["/mobile/**"],
                "rybbit_mask_patterns": ["/api/play/**", "/mobile/**"],
                "rybbit_skip_mobile_paths": True,
                "rybbit_mask_mobile_paths": True,
                "rybbit_masks_private_play_routes": True,
                "rybbit_replay_block_selector": "[data-turn-root]",
                "rybbit_replay_blocks_turn_root": True,
                "player_session_handoff_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player",
                "player_session_handoff_status": "Session handoff is ready in the link above.",
                "player_session_handoff_link_text": "Open session handoff link",
                "player_session_handoff_preserves_session": True,
                "player_session_handoff_preserves_role": True,
                "player_session_handoff_strips_device": True,
                "player_session_handoff_sender_device_id_present": True,
                "gm_route": "/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_http_status": 200,
                "gm_final_url": "https://chummer.run/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_live_turn_companion_shell": True,
                "gm_pwa_manifest_path": "/manifest.gm.webmanifest",
                "gm_pwa_role": "GameMaster",
                "gm_blazor_shell": "interactive-server",
                "gm_rybbit_configured": True,
                "gm_rybbit_tag": "mobile_play_shell",
                "gm_rybbit_route": "/mobile/gm",
                "gm_rybbit_mode": "gm",
                "gm_rybbit_role": "GameMaster",
                "gm_rybbit_site_id_present": True,
                "gm_rybbit_script_url_present": True,
                "gm_rybbit_script_url_allowed": True,
                "gm_rybbit_skip_patterns": ["/mobile/**"],
                "gm_rybbit_mask_patterns": ["/api/play/**", "/mobile/**"],
                "gm_rybbit_skip_mobile_paths": True,
                "gm_rybbit_mask_mobile_paths": True,
                "gm_rybbit_masks_private_play_routes": True,
                "gm_rybbit_replay_block_selector": "[data-turn-root]",
                "gm_rybbit_replay_blocks_turn_root": True,
                "gm_session_handoff_url": "https://chummer.run/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_session_handoff_status": "Session handoff is ready in the link above.",
                "gm_session_handoff_link_text": "Open session handoff link",
                "gm_session_handoff_preserves_session": True,
                "gm_session_handoff_preserves_role": True,
                "gm_session_handoff_strips_device": True,
                "gm_session_handoff_sender_device_id_present": True,
            },
            "ledgerArtifact": {
                "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                "ledger_primary": False,
            },
        },
    )

    assert result["status"] == "fail"
    assert result["frontdoorNavigationHomepageLaneText"] == ""
    assert result["frontdoorNavigationHomepageLaneExpected"] == "Current public lane: Stable."
    assert result["frontdoorNavigationHomepageLaneMatchesReleaseChannel"] is False
    assert "front-door navigation homepage does not disclose current public lane" in result["failures"]
    assert "front-door navigation homepage current public lane copy does not match release posture" in result["failures"]


def test_postdeploy_gate_surfaces_frontdoor_playwright_stderr_without_cascading_missing_artifact_failures() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        {
            "status": "fail",
            "exitCode": 1,
            "artifactDir": "/tmp/chummer-frontdoor-navigation",
            "mobileArtifact": {},
            "ledgerArtifact": {},
            "anchorArtifact": {},
            "stderrTail": "Error: Homepage still serves legacy release posture copy: Current release: Preview build.\\n    at assertProof (...)",
        },
    )

    assert result["status"] == "fail"
    assert result["frontdoorNavigationStatus"] == "fail"
    assert "front-door navigation Playwright proof is not pass" in result["failures"]
    assert (
        "front-door navigation Playwright proof failed before artifacts were written: "
        "Error: Homepage still serves legacy release posture copy: Current release: Preview build."
    ) in result["failures"]
    assert "front-door navigation does not gate Build" not in result["failures"]
    assert "front-door navigation mobile artifact contract is not chummer.frontdoor_mobile_launch.v2" not in result["failures"]


def test_postdeploy_gate_rejects_frontdoor_navigation_wrong_artifact_contracts() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-frontdoor-navigation",
            "mobileArtifact": {
                "contractName": "chummer.frontdoor_mobile_launch.preview",
                "gated_targets": ["Build", "Play"],
                "public_targets": [],
                "play_route": "/mobile/player",
                "play_sign_in_route": "/login?next=%2Fmobile%2Fplayer",
                "direct_player_route": "/mobile/player",
            },
            "ledgerArtifact": {
                "contractName": "chummer.black_ledger_globe_frontdoor.preview",
                "ledger_primary": False,
            },
        },
    )

    assert result["status"] == "fail"
    assert "front-door navigation mobile artifact contract is not chummer.frontdoor_mobile_launch.v2" in result["failures"]
    assert "front-door navigation ledger artifact contract is not chummer.black_ledger_globe_frontdoor.v1" in result["failures"]


def test_main_passes_custom_release_channel_receipt_to_downloads_child(monkeypatch, tmp_path) -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    release_channel = tmp_path / "custom-release-channel.json"
    release_channel.write_text('{"version":"run-20260630"}', encoding="utf-8")
    output = tmp_path / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
    commands: list[list[str]] = []

    def fake_run_child(command, output_path, allow_failure=False):  # noqa: ANN001
        commands.append(command)
        command_text = " ".join(command)
        if "check_public_edge_deploy_preflight.py" in command_text:
            return preflight
        if "verify_downloads_version_marker.py" in command_text:
            return downloads
        if "verify_public_pwa_static_assets.py" in command_text:
            return pwa_static
        if "verify_mobile_pwa_ledger_boundary.py" in command_text:
            return mobile_ledger
        if "verify_ready_mobile_handoff_contract.py" in command_text:
            return ready_mobile_handoff
        if "verify_participate_iframe_shell.py" in command_text:
            return participate_iframe_shell
        if "verify_chummer_online_launch.py" in command_text:
            return passing_online_launch_receipt()
        raise AssertionError(f"unexpected child command: {command_text}")

    monkeypatch.setattr(module, "run_child", fake_run_child)
    monkeypatch.setattr(module, "probe_role_alias_routes", lambda base_url, timeout_seconds: passing_role_alias_routes())

    exit_code = module.main(
        [
            "--base-url",
            "https://chummer.run",
            "--release-channel-receipt",
            str(release_channel),
            "--output",
            str(output),
        ]
    )

    downloads_command = next(
        command
        for command in commands
        if any("verify_downloads_version_marker.py" in item for item in command)
    )
    preflight_command = next(
        command
        for command in commands
        if any("check_public_edge_deploy_preflight.py" in item for item in command)
    )
    assert exit_code == 0
    assert "--allow-foreign-build-locks" in preflight_command
    assert "--allow-stale-foreign-build-locks" in preflight_command
    assert "--overlay-root" in preflight_command
    assert preflight_command[preflight_command.index("--overlay-root") + 1] == str(module.DEFAULT_PUBLIC_EDGE_OVERLAY_ROOT.resolve())
    assert "--release-channel-receipt" in downloads_command
    assert downloads_command[downloads_command.index("--release-channel-receipt") + 1] == str(release_channel)
    assert "--allow-non-launch-supported-release-channel" in downloads_command
    assert "--skip-release-version-match" not in downloads_command
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["skipPreflight"] is False
    assert result["skipReleaseVersionMatch"] is False
    assert result["strictPreflight"] is False
    assert result["strictInvocation"] is True
    assert result["strictNoAllowanceInvocation"] is False


def test_main_strict_preflight_runs_child_without_lock_allowances(monkeypatch, tmp_path) -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    output = tmp_path / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
    commands: list[list[str]] = []

    def fake_run_child(command, output_path, allow_failure=False):  # noqa: ANN001
        commands.append(command)
        command_text = " ".join(command)
        if "check_public_edge_deploy_preflight.py" in command_text:
            return preflight
        if "verify_downloads_version_marker.py" in command_text:
            return downloads
        if "verify_public_pwa_static_assets.py" in command_text:
            return pwa_static
        if "verify_mobile_pwa_ledger_boundary.py" in command_text:
            return mobile_ledger
        if "verify_ready_mobile_handoff_contract.py" in command_text:
            return ready_mobile_handoff
        if "verify_participate_iframe_shell.py" in command_text:
            return participate_iframe_shell
        if "verify_chummer_online_launch.py" in command_text:
            return passing_online_launch_receipt()
        raise AssertionError(f"unexpected child command: {command_text}")

    monkeypatch.setattr(module, "run_child", fake_run_child)
    monkeypatch.setattr(module, "probe_role_alias_routes", lambda base_url, timeout_seconds: passing_role_alias_routes())

    exit_code = module.main(
        [
            "--base-url",
            "https://chummer.run",
            "--strict-preflight",
            "--output",
            str(output),
        ]
    )

    preflight_command = next(
        command
        for command in commands
        if any("check_public_edge_deploy_preflight.py" in item for item in command)
    )
    assert exit_code == 0
    assert "--allow-foreign-build-locks" not in preflight_command
    assert "--allow-stale-foreign-build-locks" not in preflight_command
    assert "--overlay-root" in preflight_command
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["skipPreflight"] is False
    assert result["skipReleaseVersionMatch"] is False
    assert result["strictPreflight"] is True
    assert result["strictInvocation"] is True
    assert result["strictNoAllowanceInvocation"] is True


def test_main_passes_custom_overlay_root_to_preflight_child(monkeypatch, tmp_path) -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    output = tmp_path / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
    overlay_root = tmp_path / "overlay" / "app"
    commands: list[list[str]] = []

    def fake_run_child(command, output_path, allow_failure=False):  # noqa: ANN001
        commands.append(command)
        command_text = " ".join(command)
        if "check_public_edge_deploy_preflight.py" in command_text:
            return preflight
        if "verify_downloads_version_marker.py" in command_text:
            return downloads
        if "verify_public_pwa_static_assets.py" in command_text:
            return pwa_static
        if "verify_mobile_pwa_ledger_boundary.py" in command_text:
            return mobile_ledger
        if "verify_ready_mobile_handoff_contract.py" in command_text:
            return ready_mobile_handoff
        if "verify_participate_iframe_shell.py" in command_text:
            return participate_iframe_shell
        if "verify_chummer_online_launch.py" in command_text:
            return passing_online_launch_receipt()
        raise AssertionError(f"unexpected child command: {command_text}")

    monkeypatch.setattr(module, "run_child", fake_run_child)
    monkeypatch.setattr(module, "probe_role_alias_routes", lambda base_url, timeout_seconds: passing_role_alias_routes())

    exit_code = module.main(
        [
            "--base-url",
            "https://chummer.run",
            "--overlay-root",
            str(overlay_root),
            "--output",
            str(output),
        ]
    )

    preflight_command = next(
        command
        for command in commands
        if any("check_public_edge_deploy_preflight.py" in item for item in command)
    )
    assert exit_code == 0
    assert "--allow-foreign-build-locks" in preflight_command
    assert "--overlay-root" in preflight_command
    assert preflight_command[preflight_command.index("--overlay-root") + 1] == str(overlay_root.resolve())


def test_main_passes_release_match_skip_to_downloads_child(monkeypatch, tmp_path) -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    output = tmp_path / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
    commands: list[list[str]] = []

    def fake_run_child(command, output_path, allow_failure=False):  # noqa: ANN001
        commands.append(command)
        command_text = " ".join(command)
        if "check_public_edge_deploy_preflight.py" in command_text:
            return preflight
        if "verify_downloads_version_marker.py" in command_text:
            return downloads
        if "verify_public_pwa_static_assets.py" in command_text:
            return pwa_static
        if "verify_mobile_pwa_ledger_boundary.py" in command_text:
            return mobile_ledger
        if "verify_ready_mobile_handoff_contract.py" in command_text:
            return ready_mobile_handoff
        if "verify_participate_iframe_shell.py" in command_text:
            return participate_iframe_shell
        if "verify_chummer_online_launch.py" in command_text:
            return passing_online_launch_receipt()
        raise AssertionError(f"unexpected child command: {command_text}")

    monkeypatch.setattr(module, "run_child", fake_run_child)
    monkeypatch.setattr(module, "probe_role_alias_routes", lambda base_url, timeout_seconds: passing_role_alias_routes())

    exit_code = module.main(
        [
            "--base-url",
            "https://chummer.run",
            "--skip-release-version-match",
            "--output",
            str(output),
        ]
    )

    downloads_command = next(
        command
        for command in commands
        if any("verify_downloads_version_marker.py" in item for item in command)
    )
    assert exit_code == 0
    assert "--skip-release-version-match" in downloads_command
    assert "--allow-non-launch-supported-release-channel" not in downloads_command
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["skipPreflight"] is False
    assert result["skipReleaseVersionMatch"] is True
    assert result["strictInvocation"] is False


def test_main_records_skip_preflight_in_output(monkeypatch, tmp_path) -> None:
    module = load_module()
    _, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    output = tmp_path / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"

    def fake_run_child(command, output_path, allow_failure=False):  # noqa: ANN001
        command_text = " ".join(command)
        if "check_public_edge_deploy_preflight.py" in command_text:
            raise AssertionError("preflight child should not run when --skip-preflight is set")
        if "verify_downloads_version_marker.py" in command_text:
            return downloads
        if "verify_public_pwa_static_assets.py" in command_text:
            return pwa_static
        if "verify_mobile_pwa_ledger_boundary.py" in command_text:
            return mobile_ledger
        if "verify_ready_mobile_handoff_contract.py" in command_text:
            return ready_mobile_handoff
        if "verify_participate_iframe_shell.py" in command_text:
            return participate_iframe_shell
        if "verify_chummer_online_launch.py" in command_text:
            return passing_online_launch_receipt()
        raise AssertionError(f"unexpected child command: {command_text}")

    monkeypatch.setattr(module, "run_child", fake_run_child)
    monkeypatch.setattr(module, "probe_role_alias_routes", lambda base_url, timeout_seconds: passing_role_alias_routes())

    exit_code = module.main(
        [
            "--base-url",
            "https://chummer.run",
                "--skip-preflight",
                "--expected-full-deployment-digest-sha256",
                "b" * 64,
                "--expected-pwa-asset-inventory-sha256",
                "c" * 64,
                "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["skipPreflight"] is True
    assert result["skipReleaseVersionMatch"] is False
    assert result["strictInvocation"] is False


def test_skip_preflight_requires_external_sealed_pwa_inventory_anchor() -> None:
    module = load_module()

    with pytest.raises(SystemExit):
        module.main(
            [
                "--base-url",
                "https://chummer.run",
                "--skip-preflight",
                "--expected-full-deployment-digest-sha256",
                "b" * 64,
            ]
        )


def test_run_child_executes_from_repo_root_and_resolves_script_paths(monkeypatch, tmp_path) -> None:
    module = load_module()
    output = tmp_path / "child.json"
    output.write_text(json.dumps({"contractName": "child", "status": "pass"}), encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["command"] = command
        captured["cwd"] = kwargs.get("cwd")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.run_child(
        [sys.executable, "scripts/check_public_edge_deploy_preflight.py", "--allow-stale-foreign-build-locks"],
        output,
        allow_failure=True,
    )

    assert payload["status"] == "pass"
    assert captured["cwd"] == module.RUN_SERVICES_ROOT
    command = captured["command"]
    assert isinstance(command, list)
    assert command[1] == str(module.RUN_SERVICES_ROOT / "scripts/check_public_edge_deploy_preflight.py")
    assert command[-2:] == ["--output", str(output)]


def test_run_child_returns_synthetic_failure_when_output_is_missing(monkeypatch, tmp_path) -> None:
    module = load_module()
    output = tmp_path / "missing.json"

    def fake_run(command, **kwargs):  # noqa: ANN001
        return types.SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.run_child(
        [sys.executable, "scripts/verify_public_pwa_static_assets.py", "--base-url", "http://127.0.0.1:8091"],
        output,
        allow_failure=True,
    )

    assert payload["status"] == "fail"
    assert payload["failures"] == [
        "child verifier verify_public_pwa_static_assets did not write its receipt"
    ]
    assert payload["childId"] == "verify_public_pwa_static_assets"
    assert "childCommand" not in payload
    assert "childStdoutTail" not in payload
    assert "childStderrTail" not in payload
    assert payload["childExitCode"] == 0


def test_run_child_returns_synthetic_failure_when_output_is_not_object_json(monkeypatch, tmp_path) -> None:
    module = load_module()
    output = tmp_path / "invalid.json"
    invalid_secret = "invalid-receipt-query-secret"
    output.write_text(
        f'["https://example.test/?token={invalid_secret}"]',
        encoding="utf-8",
    )

    def fake_run(command, **kwargs):  # noqa: ANN001
        return types.SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.run_child(
        [sys.executable, "scripts/verify_public_pwa_static_assets.py", "--base-url", "http://127.0.0.1:8091"],
        output,
        allow_failure=True,
    )

    assert payload["status"] == "fail"
    assert payload["failures"] == [
        "child verifier verify_public_pwa_static_assets wrote an invalid receipt"
    ]
    assert payload["childId"] == "verify_public_pwa_static_assets"
    assert "childCommand" not in payload
    assert "childStdoutTail" not in payload
    assert "childStderrTail" not in payload
    assert payload["childExitCode"] == 0

    with pytest.raises(
        RuntimeError,
        match=(
            "^child verifier verify_public_pwa_static_assets wrote an invalid receipt$"
        ),
    ) as failure:
        module.run_child(
            [
                sys.executable,
                "scripts/verify_public_pwa_static_assets.py",
                "--base-url",
                f"https://example.test/?token={invalid_secret}",
            ],
            output,
        )
    assert invalid_secret not in str(failure.value)


def test_run_child_never_serializes_query_bearing_command_or_process_output(
    monkeypatch,
    tmp_path,
) -> None:
    module = load_module()
    output = tmp_path / "missing.json"
    command_secret = "command-query-secret"
    stdout_secret = "stdout-query-secret"
    stderr_secret = "stderr-query-secret"

    def fake_run(command, **kwargs):  # noqa: ANN001
        return types.SimpleNamespace(
            returncode=0,
            stdout=f"https://example.test/result?token={stdout_secret}\n",
            stderr=f"failed https://example.test/error?api_key={stderr_secret}\n",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.run_child(
        [
            sys.executable,
            "scripts/verify_public_pwa_static_assets.py",
            "--base-url",
            f"https://example.test/mobile?ticket={command_secret}",
        ],
        output,
        allow_failure=True,
    )

    serialized = json.dumps(payload, sort_keys=True)
    assert payload["childId"] == "verify_public_pwa_static_assets"
    assert command_secret not in serialized
    assert stdout_secret not in serialized
    assert stderr_secret not in serialized
    assert "childCommand" not in payload
    assert "childStdoutTail" not in payload
    assert "childStderrTail" not in payload


def test_run_child_sanitizes_loaded_child_diagnostics_before_return(
    monkeypatch,
    tmp_path,
) -> None:
    module = load_module()
    output = tmp_path / "child.json"
    secrets = {
        "command": "loaded-command-secret",
        "stdout": "loaded-stdout-secret",
        "stderr": "loaded-stderr-secret",
        "failure": "loaded-failure-secret",
    }
    output.write_text(
        json.dumps(
            {
                "contractName": "child",
                "status": "fail",
                "childCommand": f"tool https://example.test/?token={secrets['command']}",
                "stdoutTail": f"https://example.test/?value={secrets['stdout']}",
                "nested": {
                    "stderr": f"https://example.test/?key={secrets['stderr']}",
                },
                "failures": [
                    f"probe failed at https://example.test/?ticket={secrets['failure']}"
                ],
                "safeDetail": "query-free child validation failure",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(
            returncode=1,
            stdout="ignored raw output",
            stderr="ignored raw error",
        ),
    )

    payload = module.run_child(
        [sys.executable, "scripts/verify_public_pwa_static_assets.py"],
        output,
        allow_failure=True,
    )

    serialized = json.dumps(payload, sort_keys=True)
    assert payload["contractName"] == "child"
    assert payload["failures"] == ["[child diagnostic redacted]"]
    assert payload["safeDetail"] == "query-free child validation failure"
    assert "childCommand" not in payload
    assert "stdoutTail" not in payload
    assert payload["nested"] == {}
    assert all(secret not in serialized for secret in secrets.values())


def test_run_child_exceptions_never_interpolate_query_bearing_execution_data(
    monkeypatch,
    tmp_path,
) -> None:
    module = load_module()
    command_secret = "exception-command-secret"
    stdout_secret = "exception-stdout-secret"
    stderr_secret = "exception-stderr-secret"

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(
            returncode=9,
            stdout=f"https://example.test/?token={stdout_secret}",
            stderr=f"https://example.test/?ticket={stderr_secret}",
        ),
    )

    with pytest.raises(RuntimeError) as failure:
        module.run_child(
            [
                sys.executable,
                "scripts/verify_public_pwa_static_assets.py",
                "--base-url",
                f"https://example.test/?secret={command_secret}",
            ],
            tmp_path / "missing.json",
        )

    rendered = str(failure.value)
    assert rendered == (
        "child verifier verify_public_pwa_static_assets failed with exit code 9"
    )
    assert command_secret not in rendered
    assert stdout_secret not in rendered
    assert stderr_secret not in rendered


def test_run_child_sanitizes_process_launch_exceptions(monkeypatch, tmp_path) -> None:
    module = load_module()
    launch_secret = "process-launch-query-secret"

    def fail_to_launch(*args, **kwargs):  # noqa: ANN001
        raise OSError(f"cannot launch https://example.test/?token={launch_secret}")

    monkeypatch.setattr(module.subprocess, "run", fail_to_launch)
    command = [
        sys.executable,
        "scripts/verify_public_pwa_static_assets.py",
        "--base-url",
        f"https://example.test/?token={launch_secret}",
    ]

    payload = module.run_child(
        command,
        tmp_path / "missing.json",
        allow_failure=True,
    )
    serialized = json.dumps(payload, sort_keys=True)
    assert payload == {
        "status": "fail",
        "failures": [
            "child verifier verify_public_pwa_static_assets could not execute"
        ],
        "childId": "verify_public_pwa_static_assets",
        "childExitCode": None,
    }
    assert launch_secret not in serialized

    with pytest.raises(
        RuntimeError,
        match="^child verifier verify_public_pwa_static_assets could not execute$",
    ) as failure:
        module.run_child(command, tmp_path / "missing.json")
    assert launch_secret not in str(failure.value)


def test_run_playwright_command_executes_from_repo_root(monkeypatch) -> None:
    module = load_module()
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["command"] = command
        captured["cwd"] = kwargs.get("cwd")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    exit_code, stdout, stderr, timed_out = module.run_playwright_command(
        ["npx", "playwright", "test", "tests/public/mobile-pwa-viewport-smoke.spec.ts"],
        {"BASE_URL": "https://chummer.run"},
        30,
    )

    assert exit_code == 0
    assert stdout == ""
    assert stderr == ""
    assert timed_out is False
    assert captured["cwd"] == module.RUN_SERVICES_ROOT


def test_frontdoor_navigation_probe_uses_playwright_click_for_gm_switch(monkeypatch, tmp_path) -> None:
    module = load_module()
    captured: dict[str, object] = {}

    def fake_run_playwright_command(command, env, timeout_seconds):  # noqa: ANN001
        probe_path = tmp_path / "frontdoor-navigation-proof.cjs"
        captured["command"] = command
        captured["env"] = env
        captured["timeout_seconds"] = timeout_seconds
        captured["script"] = probe_path.read_text(encoding="utf-8")
        return 1, "", "", False

    monkeypatch.setattr(module, "run_playwright_command", fake_run_playwright_command)

    result = module.run_frontdoor_navigation_playwright("http://127.0.0.1:58182", tmp_path, 20.0)

    script = captured["script"]
    assert isinstance(script, str)
    assert "const playButton = openMenu.locator('button.site-open-chummer-menu__button[data-disabled-target=\"/mobile/player\"]'" in script
    assert "const playLink = openMenu.locator('a.site-open-chummer-menu__button[href=\"/mobile/player\"]'" not in script
    assert "gmLink.click({ noWaitAfter: true })" in script
    assert "gmLink.evaluate((element) => element.click())" not in script
    assert "channel: (process.env.CHUMMER_PLAYWRIGHT_CHANNEL || 'chromium').trim() || 'chromium'" in script
    assert "args: ['--disable-quic']" in script
    assert "const maxAttempts = 3;" in script
    assert "'net::ERR_NETWORK_CHANGED'" in script
    assert "'net::ERR_CONNECTION_RESET'" in script
    assert "if (!transient || attempt === maxAttempts)" in script
    assert "await gotoWithTransientRetry(page, baseUrl, { waitUntil: 'domcontentloaded' });" in script
    assert "new URL(directPlayerRoute || '/mobile/player', baseUrl).toString()," in script
    assert "await page.addInitScript(() => {" in script
    assert "Object.defineProperty(navigator, 'share', { configurable: true, value: undefined });" in script
    assert "Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });" in script
    assert "await page.evaluate(() => {" not in script
    assert "const proofTimeoutMs = 180000;" in script
    assert "page.waitForURL('**/mobile/gm**', { timeout: proofTimeoutMs })" in script
    assert "await page.close({ runBeforeUnload: false }).catch(() => undefined);" in script
    assert "const anchorPage = await browser.newPage({ viewport: mobileViewport });" in script
    assert "const anchorEntryUrl = new URL('/#turn-runsite-card', baseUrl).toString();" in script
    assert "await anchorPage.waitForFunction(() => {" in script
    assert "}, null, { timeout: proofTimeoutMs });" in script
    assert "currentUrl.pathname === '/mobile/player'" in script
    assert "currentUrl.hash === '#turn-runsite-card'" in script
    assert "currentUrl.search === '';" in script
    assert "contractName: 'chummer.frontdoor_mobile_launch.v2'" in script
    assert "contractName: 'chummer.frontdoor_mobile_anchor_redirect.v2'" in script
    assert "player_session_handoff_url: redactedPrivateUrl(playerHandoffUrl.toString())" in script
    assert "gm_session_handoff_url: redactedPrivateUrl(gmHandoffUrl.toString())" in script
    assert "visible_player_url_private_identity_absent: visibleRoleUrlIsPathOnly(finalUrl, '/mobile/player')" in script
    assert "player_session_context_present: Boolean(playerSessionId)" in script
    assert "player_device_context_present: Boolean(playerDeviceId)" in script
    assert "visible_gm_url_private_identity_absent: visibleRoleUrlIsPathOnly(gmFinalUrl, '/mobile/gm')" in script
    assert "gm_session_context_present: Boolean(gmSessionId)" in script
    assert "gm_device_context_present: Boolean(gmDeviceId)" in script
    assert "final_url: anchorFinalUrlText" in script
    assert "\n      session_id_present:" not in script
    assert "\n      device_id_present:" not in script
    assert "const legacyHomepageLaneMatch = heroText.match(/Current release:\\s*(Stable\\.|Preview build\\.|Downloads paused\\.)/);" in script
    assert "Homepage still serves legacy release posture copy:" in script
    assert "status: anchorStatus," in script
    assert "failure: anchorFailure," in script
    assert "page_errors: anchorPageErrors.map(redactPrivateText)," in script
    assert "if (anchorFailure) {" in script
    assert "writeJson('FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json'" in script
    assert result["status"] == "fail"


def test_frontdoor_navigation_can_reuse_existing_artifacts(monkeypatch, tmp_path) -> None:
    module = load_module()
    (tmp_path / "FRONTDOOR_MOBILE_LAUNCH.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.frontdoor_mobile_launch.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "entry_url": "https://chummer.run/#turn-runsite-card?",
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player#turn-runsite-card",
                "final_pathname": "/mobile/player",
                "final_hash": "#turn-runsite-card",
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "session_id_present": True,
                "device_id_present": True,
            }
        ),
        encoding="utf-8",
    )

    write_passing_frontdoor_artifacts(tmp_path)

    def unexpected_run(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("Playwright should not run when reusable frontdoor artifacts already exist.")

    monkeypatch.setattr(module, "run_playwright_command", unexpected_run)

    result = module.run_frontdoor_navigation_playwright(
        "https://chummer.run",
        tmp_path,
        20.0,
        reuse_existing_artifact=True,
    )

    assert result["status"] == "pass"
    assert result["exitCode"] == 0
    assert result["artifactReused"] is True
    assert result["playwrightExecuted"] is False
    assert result["mobileArtifactContract"] == "chummer.frontdoor_mobile_launch.v2"
    assert result["ledgerArtifactContract"] == "chummer.black_ledger_globe_frontdoor.v1"
    assert result["anchorArtifactContract"] == "chummer.frontdoor_mobile_anchor_redirect.v2"
    assert result["mobileArtifactBaseUrlMatchesRequested"] is True
    assert result["ledgerArtifactBaseUrlMatchesRequested"] is True
    assert result["anchorArtifactBaseUrlMatchesRequested"] is True
    assert result["mobileArtifactFresh"] is True
    assert result["ledgerArtifactFresh"] is True
    assert result["anchorArtifactFresh"] is True
    assert result["mobileHomepageLaneMatchesExpected"] is True
    assert result["mobileArtifactPrivacyContractSatisfied"] is True
    assert result["anchorArtifactCurrentContractSatisfied"] is True


def test_frontdoor_navigation_rejects_raw_private_reuse_and_redacts_receipt_logs(monkeypatch, tmp_path) -> None:
    module = load_module()
    write_passing_frontdoor_artifacts(tmp_path)
    mobile_path = tmp_path / "FRONTDOOR_MOBILE_LAUNCH.generated.json"
    anchor_path = tmp_path / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json"
    mobile = json.loads(mobile_path.read_text(encoding="utf-8"))
    mobile["final_url"] = "https://chummer.run/mobile/player?sessionId=reuse-private-session"
    mobile["player_session_handoff_url"] = (
        "https://chummer.run/mobile/player?sessionId=reuse-private-session&role=Player"
    )
    mobile_path.write_text(json.dumps(mobile), encoding="utf-8")
    anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    anchor["final_url"] = (
        "https://chummer.run/mobile/player?sessionId=reuse-private-session"
        "&deviceId=reuse-private-device#turn-runsite-card"
    )
    anchor_path.write_text(json.dumps(anchor), encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run_playwright_command(command, env, timeout_seconds):  # noqa: ANN001
        captured["command"] = command
        write_passing_frontdoor_artifacts(tmp_path)
        return (
            0,
            "navigated sessionId=reuse-private-session\n",
            'device {"deviceId":"reuse-private-device"}\n',
            False,
        )

    monkeypatch.setattr(module, "run_playwright_command", fake_run_playwright_command)

    result = module.run_frontdoor_navigation_playwright(
        "https://chummer.run",
        tmp_path,
        20.0,
        reuse_existing_artifact=True,
    )

    serialized = json.dumps(result)
    assert "command" in captured
    assert result["status"] == "pass"
    assert result["artifactReused"] is False
    assert result["playwrightExecuted"] is True
    assert "reuse-private-session" not in serialized
    assert "reuse-private-device" not in serialized
    assert "sessionId=[redacted]" in result["stdoutTail"]
    assert 'deviceId":"[redacted]' in result["stderrTail"]


def test_postdeploy_gate_fails_closed_and_redacts_raw_frontdoor_child_receipt() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    frontdoor = passing_frontdoor_navigation()
    mobile = frontdoor["mobileArtifact"]
    anchor = frontdoor["anchorArtifact"]
    assert isinstance(mobile, dict)
    assert isinstance(anchor, dict)
    mobile["final_url"] = "https://chummer.run/mobile/player?sessionId=receipt-private-session"
    mobile["player_session_handoff_url"] = (
        "https://chummer.run/mobile/player?sessionId=receipt-private-session&role=Player"
    )
    anchor["final_url"] = (
        "https://chummer.run/mobile/player?sessionId=receipt-private-session"
        "&deviceId=receipt-private-device#turn-runsite-card"
    )

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        frontdoor,
    )

    serialized = json.dumps(result)
    assert result["status"] == "fail"
    assert "front-door navigation mobile artifact contains raw private session or device identity" in result["failures"]
    assert "front-door navigation anchor artifact contains raw private session or device identity" in result["failures"]
    assert "receipt-private-session" not in serialized
    assert "receipt-private-device" not in serialized
    assert "sessionId=[redacted]" in serialized
    assert "deviceId=[redacted]" in serialized


def test_frontdoor_navigation_reruns_when_reused_homepage_lane_text_mismatches_expected(monkeypatch, tmp_path) -> None:
    module = load_module()
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    (tmp_path / "FRONTDOOR_MOBILE_LAUNCH.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.frontdoor_mobile_launch.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": generated_at,
                "homepage_lane_text": "Current public lane: Preview. Review required.",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": generated_at,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": generated_at,
                "entry_url": "https://chummer.run/#turn-runsite-card",
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player#turn-runsite-card",
                "final_pathname": "/mobile/player",
                "final_hash": "#turn-runsite-card",
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "session_id_present": True,
                "device_id_present": True,
            }
        ),
        encoding="utf-8",
    )

    write_passing_frontdoor_artifacts(
        tmp_path,
        homepage_lane_text="Current public lane: Preview. Review required.",
    )
    captured: dict[str, object] = {}

    def fake_run_playwright_command(command, env, timeout_seconds):  # noqa: ANN001
        captured["command"] = command
        captured["env"] = env
        captured["timeout_seconds"] = timeout_seconds
        (tmp_path / "FRONTDOOR_MOBILE_LAUNCH.generated.json").write_text(
            json.dumps(
                {
                    "contractName": "chummer.frontdoor_mobile_launch.v1",
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": generated_at,
                    "homepage_lane_text": "Current public lane: Stable.",
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json").write_text(
            json.dumps(
                {
                    "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": generated_at,
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json").write_text(
            json.dumps(
                {
                    "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": generated_at,
                    "entry_url": "https://chummer.run/#turn-runsite-card",
                    "final_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player#turn-runsite-card",
                    "final_pathname": "/mobile/player",
                    "final_hash": "#turn-runsite-card",
                    "pwa_manifest_path": "/manifest.player.webmanifest",
                    "pwa_role": "Player",
                    "blazor_shell": "interactive-server",
                    "session_id_present": True,
                    "device_id_present": True,
                }
            ),
            encoding="utf-8",
        )
        write_passing_frontdoor_artifacts(tmp_path)
        return 0, "", "", False

    monkeypatch.setattr(module, "run_playwright_command", fake_run_playwright_command)

    result = module.run_frontdoor_navigation_playwright(
        "https://chummer.run",
        tmp_path,
        20.0,
        reuse_existing_artifact=True,
        expected_homepage_lane_text="Current public lane: Stable.",
    )

    assert "command" in captured
    assert result["status"] == "pass"
    assert result["artifactReused"] is False
    assert result["playwrightExecuted"] is True
    assert result["mobileArtifact"]["homepage_lane_text"] == "Current public lane: Stable."


def test_frontdoor_navigation_reuses_canonical_anchor_artifact(monkeypatch, tmp_path) -> None:
    module = load_module()
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    (tmp_path / "FRONTDOOR_MOBILE_LAUNCH.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.frontdoor_mobile_launch.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": generated_at,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": generated_at,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": generated_at,
                "entry_url": "https://chummer.run/#turn-runsite-card",
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player#turn-runsite-card",
                "final_pathname": "/mobile/player",
                "final_hash": "#turn-runsite-card",
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "session_id_present": True,
                "device_id_present": True,
            }
        ),
        encoding="utf-8",
    )

    write_passing_frontdoor_artifacts(tmp_path)
    captured: dict[str, object] = {}

    def fake_run_playwright_command(command, env, timeout_seconds):  # noqa: ANN001
        captured["command"] = command
        (tmp_path / "FRONTDOOR_MOBILE_LAUNCH.generated.json").write_text(
            json.dumps(
                {
                    "contractName": "chummer.frontdoor_mobile_launch.v1",
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": generated_at,
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json").write_text(
            json.dumps(
                {
                    "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": generated_at,
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json").write_text(
            json.dumps(
                {
                    "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": generated_at,
                    "entry_url": "https://chummer.run/#turn-runsite-card?",
                    "final_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player#turn-runsite-card",
                    "final_pathname": "/mobile/player",
                    "final_hash": "#turn-runsite-card",
                    "pwa_manifest_path": "/manifest.player.webmanifest",
                    "pwa_role": "Player",
                    "blazor_shell": "interactive-server",
                    "session_id_present": True,
                    "device_id_present": True,
                }
            ),
            encoding="utf-8",
        )
        return 0, "", "", False

    monkeypatch.setattr(module, "run_playwright_command", fake_run_playwright_command)

    result = module.run_frontdoor_navigation_playwright(
        "https://chummer.run",
        tmp_path,
        20.0,
        reuse_existing_artifact=True,
    )

    assert "command" not in captured
    assert result["status"] == "pass"
    assert result["artifactReused"] is True
    assert result["playwrightExecuted"] is False
    assert result["anchorArtifact"]["entry_url"] == "https://chummer.run/#turn-runsite-card"
    assert result["mobileArtifactPrivacyContractSatisfied"] is True
    assert result["anchorArtifactCurrentContractSatisfied"] is True


def test_frontdoor_navigation_clears_stale_artifacts_and_surfaces_failed_anchor_artifact(monkeypatch, tmp_path) -> None:
    module = load_module()
    (tmp_path / "FRONTDOOR_MOBILE_LAUNCH.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.frontdoor_mobile_launch.v1",
                "status": "pass",
                "base_url": "https://stale.example",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                "status": "pass",
                "base_url": "https://stale.example",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                "status": "pass",
                "base_url": "https://stale.example",
            }
        ),
        encoding="utf-8",
    )

    def fake_run_playwright_command(command, env, timeout_seconds):  # noqa: ANN001
        (tmp_path / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json").write_text(
            json.dumps(
                {
                    "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                    "status": "fail",
                    "base_url": "https://chummer.run",
                    "entry_url": "https://chummer.run/#turn-runsite-card?",
                    "final_url": "https://chummer.run/#turn-runsite-card",
                    "final_pathname": "/",
                    "final_hash": "#turn-runsite-card",
                    "pwa_manifest_path": "/manifest.webmanifest",
                    "pwa_role": None,
                    "blazor_shell": None,
                    "session_id_present": False,
                    "device_id_present": False,
                    "failure": "Homepage anchor redirect did not land on /mobile/player",
                }
            ),
            encoding="utf-8",
        )
        return 1, "", "anchor failed\n", False

    monkeypatch.setattr(module, "run_playwright_command", fake_run_playwright_command)

    result = module.run_frontdoor_navigation_playwright("https://chummer.run", tmp_path, 20.0)

    assert result["status"] == "fail"
    assert result["mobileArtifactContract"] == ""
    assert result["ledgerArtifactContract"] == ""
    assert result["anchorArtifactContract"] == "chummer.frontdoor_mobile_anchor_redirect.v1"
    assert result["anchorArtifactBaseUrlMatchesRequested"] is True
    assert result["anchorArtifact"]["status"] == "fail"
    assert result["anchorArtifact"]["final_pathname"] == "/"
    assert result["anchorArtifact"]["final_hash"] == "#turn-runsite-card"


def test_mobile_rybbit_smoke_asset_exists_for_local_frontdoor_probe() -> None:
    asset_path = REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / "mobile-rybbit-smoke.js"
    script = asset_path.read_text(encoding="utf-8")

    assert asset_path.is_file()
    assert "window.rybbit" in script
    assert "track: function () {}" in script
    assert "event: function () {}" in script
