from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_mobile_pwa_public_projection.py"
DESIGN_SPEC_CANDIDATES = (
    REPO_ROOT.parent / "chummer-design" / "products" / "chummer" / "MOBILE_PWA_PRODUCT_SPEC.md",
    Path("/docker/chummercomplete/chummer-design/products/chummer/MOBILE_PWA_PRODUCT_SPEC.md"),
)


class _FakeResponse:
    def __init__(
        self,
        url: str,
        *,
        status_code: int = 200,
        text: str = "",
        json_data: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.text = text
        self._json_data = json_data
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"unexpected status {self.status_code}")

    def json(self) -> object:
        return self._json_data


class _FakeSession:
    def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
        del timeout, allow_redirects
        if url.rstrip("/") == "http://example.test":
            return _FakeResponse(
                url,
                text=(
                    '<details class="site-account-menu site-open-chummer-menu">'
                    '<summary><span>Open Chummer</span></summary>'
                    '<div aria-label="Open Chummer options">'
                    '<button class="site-open-chummer-menu__button" type="button" disabled data-analytics-label="Build">Build</button>'
                    '<a class="site-open-chummer-menu__button" href="/mobile/player" data-analytics-label="Play">Play</a>'
                    "</div></details>"
                ),
            )
        if url.endswith("/build"):
            return _FakeResponse(
                "http://example.test/app?command=character_roster",
                text="<section id=\"chummer-online-app\" class=\"browser-app-roster\"><span>Chummer Online</span><h1>Character Roster</h1></section>",
            )
        if url.endswith("/mobile"):
            return _FakeResponse(
                url,
                text=(
                    '<link rel="manifest" href="/manifest.json">'
                    '<script>serviceWorker.register("/service-worker.js?v=test")</script>'
                    "Install this app /play/continuity"
                ),
            )
        if url.endswith("/pwa"):
            return _FakeResponse(f"{url[:-4]}/mobile")
        if url.endswith("/play"):
            return _FakeResponse(
                url,
                text=(
                    '<section id="pwa-ledger-stream">'
                    '<p data-pwa-install-state>Installable app shell live</p>'
                    '<p data-pwa-ledger-status>Checking</p>'
                    '<meter data-pwa-ledger-heat-meter></meter>'
                    "</section>"
                ),
            )
        if url.endswith("/player"):
            return _FakeResponse(f"{url[:-7]}/play?role=player")
        if url.endswith("/gm"):
            return _FakeResponse(f"{url[:-3]}/play?role=gm")
        if url.endswith("/observer"):
            return _FakeResponse(f"{url[:-9]}/play?role=observer")
        if url.endswith("/session"):
            return _FakeResponse(f"{url[:-8]}/play")
        if url.endswith("/play/continuity"):
            return _FakeResponse(url, text="continuity")
        if url.endswith("/mobile/pwa.json"):
            return _FakeResponse(
                url,
                json_data={
                    "install_route": "/downloads",
                    "continuity_route": "/play/continuity",
                    "receipt_index_route": "/play/continuity/history",
                },
            )
        if url.endswith("/mobile/pwa/ledger.json"):
            return _FakeResponse(
                url,
                json_data={
                    "mode": "mobile_pwa_living_world",
                    "status": "opt_in_required",
                    "status_label": "Opt in required",
                    "summary": "Black Ledger live updates are available in the PWA when you opt in via account preferences.",
                    "legal_posture": "Public lane stays aggregate only. No private run table state, world heat, followed-world selection, or session continuity payload is published before opt-in.",
                    "opt_in_route": "/account",
                    "world_gate": "account_opt_in_and_followed_world_selection",
                    "heat_visibility": "hidden_until_opt_in",
                    "session_visibility": "hidden_until_opt_in",
                    "opt_in_required_for": [
                        "black_ledger_heat",
                        "followed_world_updates",
                        "session_continuity",
                    ],
                    "updates_route": "/mobile/pwa/ledger.json",
                },
                headers={
                    "Cache-Control": "private, no-store, no-cache, max-age=0",
                    "Vary": "Cookie, Authorization",
                },
            )
        if url.endswith("/play/continuity/receipts") or url.endswith("/play/continuity/history"):
            return _FakeResponse(
                url,
                json_data={
                    "boundary": "first-party only",
                    "receipts": [{"id": "one"}, {"id": "two"}, {"id": "three"}],
                },
            )
        if url.endswith("/manifest.json"):
            return _FakeResponse(
                url,
                json_data={
                    "id": "/mobile",
                    "start_url": "/mobile",
                    "display": "standalone",
                    "display_override": ["window-controls-overlay"],
                    "shortcuts": [
                        {"url": "/mobile"},
                        {"url": "/play"},
                        {"url": "/play/continuity"},
                    ],
                    "screenshots": [{"src": "/one.png"}, {"src": "/two.png"}],
                    "icons": [{"src": "/icon.png"}],
                },
            )
        if "/service-worker.js" in url:
            return _FakeResponse(
                url,
                text=(
                    'self.addEventListener("fetch", () => {});\n'
                    'self.addEventListener("push", () => {});\n'
                    'self.addEventListener("notificationclick", () => {});\n'
                    'self.addEventListener("notificationclose", () => {});\n'
                    "navigationPreload\n"
                    "RUNTIME_CACHE\n"
                    'const PRECACHE_URLS = ["/mobile", "/play", "/play/continuity", "/mobile/pwa.json", "/ready/handoff/mobile.json"];\n'
                    'const NON_CACHEABLE_PATHS = new Set(["/mobile/pwa/ledger.json"]);\n'
                    'const NOTIFICATION_ROUTE_PATHS = new Set(["/account/ledger/notifications", "/mobile", "/play", "/play/continuity", "/ledger/map", "/passport"]);\n'
                    'const NOTIFICATION_ROUTE_PREFIXES = ["/account/ledger/factions/", "/ledger/turns/", "/ledger/newsroom/", "/passport/receipts/"];\n'
                    'const NOTIFICATION_ASSET_PATHS = new Set(["/apple-touch-icon.png", "/favicon.ico", "/favicon.svg", "/pwa-icon.svg"]);\n'
                    'const NOTIFICATION_ASSET_SUFFIXES = [".ico", ".png", ".svg", ".webp"];\n'
                    "tryNormalizeNotificationHref(value);\n"
                    "isAllowedNotificationHref(pathname);\n"
                    "tryNormalizeNotificationAssetPath(value);\n"
                    "isAllowedNotificationAssetPath(pathname);\n"
                ),
            )
        raise AssertionError(f"unexpected url {url}")


def _load_module():
    scripts_dir = str(SCRIPT_PATH.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("verify_mobile_pwa_public_projection", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load verifier module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MobilePwaPublicProjectionTests(unittest.TestCase):
    def test_design_spec_tracks_live_pwa_projection_contract(self) -> None:
        design_spec_path = next((path for path in DESIGN_SPEC_CANDIDATES if path.is_file()), None)
        if design_spec_path is None:
            self.skipTest("chummer-design checkout is not available")
        text = design_spec_path.read_text(encoding="utf-8")

    payload = module.source_topology(ROOT)

    assert payload["status"] == "pass", payload["failures"]
    assert payload["topology"] == {
        "privatePlayProfileOnly": True,
        "publicProjectionDefaultOff": True,
        "edgeServiceKeyAbsent": True,
        "edgeUpstreamAbsent": True,
        "portalHasNoPlayDependency": True,
    }
    assert payload["gateway"]["zeroPublicPaths"] is True
    assert payload["gateway"]["noHttpClient"] is True
    assert payload["gateway"]["notInRequestPipeline"] is True
    assert payload["readiness"]["combinedBodyReturned"] is True
    assert payload["roleShell"]["playAppliesPrivateHeaders"] is True
    assert payload["roleShell"]["roleFieldsInModel"] is True
    assert all(payload["retiredEnvAbsent"].values())

    def test_public_role_aliases_converge_on_play_shell_not_mobile_subroutes(self) -> None:
        controller = (REPO_ROOT / "Chummer.Run.Api/Controllers/PublicLandingController.cs").read_text(encoding="utf-8")

        for role in ("player", "gm", "observer"):
            expected = f'=> Redirect("/play?role={role}");'
            self.assertIn(expected, controller)
            self.assertNotIn(f'=> Redirect("/mobile/{role}");', controller)

    def test_live_update_actions_use_product_routes_not_json_endpoints(self) -> None:
        controller = (REPO_ROOT / "Chummer.Run.Api/Controllers/PublicLandingController.cs").read_text(encoding="utf-8")
        mobile_view = (REPO_ROOT / "Chummer.Run.Api/Views/PublicLanding/MobileProjection.cshtml").read_text(encoding="utf-8")

        self.assertIn('href="/ledger/turns/1">Open live update</a>', mobile_view)
        self.assertIn('newsreel_route = (string?)$"/ledger/turns/{world.CurrentTurn}"', controller)
        self.assertNotIn('data-pwa-ledger-newsreel-route href="/ledger/turns/1/newsreel.json"', mobile_view)
        self.assertNotIn('"/ledger/turns/" + payload.continuity.turn + "/newsreel.json"', mobile_view)
        self.assertNotIn('newsreel_route = (string?)$"/ledger/turns/{world.CurrentTurn}/newsreel.json"', controller)

    def test_verifier_prints_explicit_ok_line_on_pass(self) -> None:
        module = _load_module()
        stdout = io.StringIO()
        captured_payloads: list[dict] = []

        with (
            patch.object(module.requests, "Session", return_value=_FakeSession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json", side_effect=lambda _path, payload: captured_payloads.append(payload)),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.run("http://example.test")

        self.assertEqual(result, 0)
        self.assertIn("mobile_pwa_public_projection:ok", stdout.getvalue())
        self.assertTrue(any(check["id"] == "ledger_stream_opt_in_boundary_holds" and check["pass"] for check in captured_payloads[0]["checks"]))
        self.assertTrue(any(check["id"] == "home_open_chummer_dropdown_routes_build_and_play" and check["pass"] for check in captured_payloads[0]["checks"]))
        self.assertTrue(any(check["id"] == "build_route_opens_character_roster" and check["pass"] for check in captured_payloads[0]["checks"]))
        self.assertTrue(any(check["id"] == "play_route_opens_pwa_play_shell" and check["pass"] for check in captured_payloads[0]["checks"]))
        self.assertTrue(captured_payloads[0]["public_entry"]["home_open_chummer_dropdown_holds"])
        self.assertTrue(captured_payloads[0]["public_entry"]["build_route_holds"])
        self.assertTrue(captured_payloads[0]["public_entry"]["play_shell_holds"])

    assert not any(result.values())
    assert len(failures) == len(result)

        module = _load_module()
        stdout = io.StringIO()
        captured_payloads: list[dict] = []

        with (
            patch.object(module.requests, "Session", return_value=DriftedSession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json", side_effect=lambda _path, payload: captured_payloads.append(payload)),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.run("http://example.test")

        self.assertEqual(result, 1)
        self.assertNotIn("mobile_pwa_public_projection:ok", stdout.getvalue())
        self.assertIn("mobile_pwa_public_projection:fail", stdout.getvalue())
        self.assertEqual(captured_payloads[0]["status"], "fail")
        self.assertIn("checks", captured_payloads[0])
        self.assertTrue(any(check["id"] == "role_routes_hold" and check["pass"] is False for check in captured_payloads[0]["checks"]))
        self.assertTrue(any("role_routes_hold" in failure for failure in captured_payloads[0]["failures"]))

    def test_verifier_fails_when_home_open_chummer_drops_play_route(self) -> None:
        class DriftedSession(_FakeSession):
            def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
                response = super().get(url, timeout=timeout, allow_redirects=allow_redirects)
                if url.rstrip("/") == "http://example.test":
                    return _FakeResponse(response.url, text=response.text.replace('href="/mobile/player"', 'href="/account"', 1))
                return response

        module = _load_module()
        stdout = io.StringIO()
        captured_payloads: list[dict] = []

        with (
            patch.object(module.requests, "Session", return_value=DriftedSession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json", side_effect=lambda _path, payload: captured_payloads.append(payload)),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.run("http://example.test")

        self.assertEqual(result, 1)
        self.assertNotIn("mobile_pwa_public_projection:ok", stdout.getvalue())
        self.assertTrue(
            any(
                check["id"] == "home_open_chummer_dropdown_routes_build_and_play" and check["pass"] is False
                for check in captured_payloads[0]["checks"]
            )
        )
        self.assertIn('href="/mobile/player"', captured_payloads[0]["public_entry"]["home_open_chummer_missing_markers"])

    def test_verifier_fails_when_build_route_stops_opening_character_roster(self) -> None:
        class DriftedSession(_FakeSession):
            def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
                if url.endswith("/build"):
                    return _FakeResponse("http://example.test/build", text="<main>Build unavailable</main>")
                return super().get(url, timeout=timeout, allow_redirects=allow_redirects)

        module = _load_module()
        stdout = io.StringIO()
        captured_payloads: list[dict] = []

        with (
            patch.object(module.requests, "Session", return_value=DriftedSession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json", side_effect=lambda _path, payload: captured_payloads.append(payload)),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.run("http://example.test")

        self.assertEqual(result, 1)
        self.assertNotIn("mobile_pwa_public_projection:ok", stdout.getvalue())
        self.assertTrue(any(check["id"] == "build_route_opens_character_roster" and check["pass"] is False for check in captured_payloads[0]["checks"]))
        self.assertEqual(captured_payloads[0]["public_entry"]["build_final_route"], "/build")

    def test_verifier_accepts_legacy_preview_shell_marker_for_build_route(self) -> None:
        class LegacyShellSession(_FakeSession):
            def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
                if url.endswith("/build"):
                    return _FakeResponse(
                        "http://example.test/app?command=character_roster",
                        text="<main class=\"browser-preview-shell\"><h1>Character Roster</h1><p>Chummer Online</p></main>",
                    )
                return super().get(url, timeout=timeout, allow_redirects=allow_redirects)

        module = _load_module()
        stdout = io.StringIO()
        captured_payloads: list[dict] = []

        with (
            patch.object(module.requests, "Session", return_value=LegacyShellSession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json", side_effect=lambda _path, payload: captured_payloads.append(payload)),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.run("http://example.test")

        self.assertEqual(result, 0)
        self.assertIn("mobile_pwa_public_projection:ok", stdout.getvalue())
        self.assertTrue(captured_payloads[0]["public_entry"]["build_route_holds"])

    def test_verifier_supports_explicit_output_and_report_paths(self) -> None:
        module = _load_module()
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "mobile-pwa.json"
            report = Path(temp_dir) / "mobile-pwa.md"
            with (
                patch.object(module.requests, "Session", return_value=_FakeSession()),
                patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
                redirect_stdout(stdout),
            ):
                result = module.run("http://example.test", output_path=output, report_path=report)

            self.assertEqual(result, 0)
            self.assertTrue(output.is_file())
            self.assertTrue(report.is_file())
            self.assertIn(str(output), stdout.getvalue())
            self.assertIn('"status": "pass"', output.read_text(encoding="utf-8"))
            self.assertIn("- Status: `pass`", report.read_text(encoding="utf-8"))


class FakeSession:
    def __init__(self, *, readiness_status: int = 200, readiness_ready: bool = True):
        self.readiness_status = readiness_status
        self.readiness_ready = readiness_ready

    def get(self, url: str, timeout: int = 30, allow_redirects: bool = True):
        if url.endswith("/api/ready"):
            return FakeResponse(
                self.readiness_status,
                payload={
                    "ready": self.readiness_ready,
                    "status": "ready" if self.readiness_ready else "not_ready",
                    "hub": {"ready": True, "status": "pass"},
                    "playProjection": {"status": "disabled", "ready": True, "enabled": False},
                    "deploymentIdentity": {
                        "ready": True,
                        "code": "overlay_identity_bound",
                        "sourceFingerprintSha256": "ab" * 32,
                    },
                },
            )
        values = parse_qs(urlsplit(url).query, keep_blank_values=True).get("role", [])
        normalized = values[0].strip().lower() if len(values) == 1 else ""
        role = (
            "gm"
            if normalized in {"gm", "game-master", "gamemaster"}
            else "observer"
            if normalized in {"observer", "spectator", "viewer"}
            else "player"
        )
        manifest = f"/manifest.{role}.webmanifest"
        title = "Chummer Observer" if role == "observer" else "Chummer GM" if role == "gm" else "Chummer Player"
        purpose = {
            "player": "Keep your runner ready at the table.",
            "gm": "Stage the table without exposing Game Master controls.",
            "observer": "Follow the table without gaining control.",
        }[role]
        capability = {
            "player": "Runner readiness",
            "gm": "Scene pacing",
            "observer": "Read-mostly return",
        }[role]
        target = f"/mobile/{role}"
        return FakeResponse(
            200,
            text=(
                f'<title>Install {title} Companion</title>'
                f'<link rel="manifest" href="{manifest}">'
                f'<main data-install-role="{role}" data-play-surface="install-only" '
                f'data-mobile-app-path="{target}">'
                f'<h1>{purpose}</h1><h2>{capability}</h2>'
                f'<a href="{target}">Open</a><svg data-mobile-app-inline-qr></svg>'
                f'<section data-role-privacy-warning="{role}"></section>'
                f'<section data-role-authority-warning="{role}"></section>'
                f'{title}</main>'
                '<script src="/mobile-install-shell.js"></script>'
            ),
            headers={
                "Cache-Control": "private, no-store",
                "Content-Security-Policy": "default-src 'none'; connect-src 'none'",
            },
            url=f"https://example.test{target}",
            history=[FakeResponse(302, headers={"Location": target}, url=url)],
        )


class PassingStaticVerifier:
    @staticmethod
    def verify_live(base_url: str, timeout: float):
        return {"status": "pass", "failures": [], "baseUrl": base_url, "timeout": timeout}


def test_live_contract_accepts_truthful_readiness_and_role_specific_install_shells(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "load_static_verifier", lambda: PassingStaticVerifier)

    payload = module.live_projection("https://example.test", session=FakeSession())

    assert payload["status"] == "pass", payload["failures"]
    assert payload["readiness"]["payload"]["ready"] is True
    assert set(payload["roleShells"]) == {"player", "gm", "observer"}
    assert all(all(checks.values()) for checks in payload["roleShells"].values())
    assert set(payload["roleProbes"]) == {probe[0] for probe in module.ROLE_PROBES}
    assert all(
        all(result["checks"].values())
        for result in payload["roleProbes"].values()
    )
    assert payload["roleProbes"]["repeated_roles"]["expectedRole"] == "player"
    assert payload["roleProbes"]["unknown_role"]["expectedRole"] == "player"
    assert payload["roleProbes"]["mixed_case_alias"]["expectedRole"] == "gm"
    assert all(
        "?" not in location and "must-not-survive" not in location
        for result in payload["roleProbes"].values()
        for location in result["redirectLocations"]
    )


def test_live_contract_rejects_readiness_body_status_contradiction(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "load_static_verifier", lambda: PassingStaticVerifier)

    payload = module.live_projection(
        "https://example.test",
        session=FakeSession(readiness_status=503, readiness_ready=True),
    )

    assert payload["status"] == "fail"
    assert "/api/ready: http200 failed" in payload["failures"]


def test_live_contract_rejects_missing_failed_or_incomplete_hub_truth(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "load_static_verifier", lambda: PassingStaticVerifier)

    class InvalidHubSession(FakeSession):
        def __init__(self, hub_payload, *, top_status="ready"):
            super().__init__()
            self.hub_payload = hub_payload
            self.top_status = top_status

        def get(self, url: str, timeout: int = 30, allow_redirects: bool = True):
            response = super().get(url, timeout, allow_redirects)
            if url.endswith("/api/ready"):
                response._payload["status"] = self.top_status
                if self.hub_payload is None:
                    response._payload.pop("hub", None)
                else:
                    response._payload["hub"] = self.hub_payload
            return response

    cases = (
        (None, "ready", "hubObject"),
        ({"ready": False, "status": "fail"}, "ready", "hubReady"),
        ({"ready": True}, "ready", "hubStatus"),
        ({"ready": True, "status": "pass"}, "not_ready", "bodyStatus"),
    )
    for hub_payload, top_status, failed_check in cases:
        payload = module.live_projection(
            "https://example.test",
            session=InvalidHubSession(hub_payload, top_status=top_status),
        )
        assert payload["status"] == "fail"
        assert payload["readiness"]["checks"][failed_check] is False
        assert payload["readiness"]["checks"]["combinedConsistent"] is False


def test_live_contract_rejects_unbound_deployment_identity(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "load_static_verifier", lambda: PassingStaticVerifier)

    class UnboundIdentitySession(FakeSession):
        def get(self, url: str, timeout: int = 30, allow_redirects: bool = True):
            response = super().get(url, timeout, allow_redirects)
            if url.endswith("/api/ready"):
                response._payload["deploymentIdentity"] = {
                    "ready": False,
                    "code": "overlay_identity_invalid",
                    "sourceFingerprintSha256": None,
                }
            return response

    payload = module.live_projection(
        "https://example.test",
        session=UnboundIdentitySession(),
    )

    assert payload["status"] == "fail"
    assert payload["readiness"]["checks"]["deploymentIdentityReady"] is False
    assert payload["readiness"]["checks"]["deploymentIdentityCode"] is False
    assert payload["readiness"]["checks"]["deploymentIdentityFingerprint"] is False


def test_live_contract_rejects_generic_or_noncanonical_role_shell(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "load_static_verifier", lambda: PassingStaticVerifier)

    class GenericShellSession(FakeSession):
        def get(self, url: str, timeout: int = 30, allow_redirects: bool = True):
            response = super().get(url, timeout, allow_redirects)
            if url.endswith("/api/ready"):
                return response
            response.text = response.text.replace("Scene pacing", "Generic companion")
            response.url = f"{url}&secret=must-not-survive"
            response.history = []
            return response

    payload = module.live_projection("https://example.test", session=GenericShellSession())

    assert payload["status"] == "fail"
    assert "gm (/play?role=gm): capability failed" in payload["failures"]
    assert "gm (/play?role=gm): exactlyOneRedirect failed" in payload["failures"]
    assert "gm (/play?role=gm): cleanFinalUrl failed" in payload["failures"]


def test_live_contract_rejects_multi_hop_or_secret_bearing_redirect_history(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "load_static_verifier", lambda: PassingStaticVerifier)

    class LeakyHistorySession(FakeSession):
        def get(self, url: str, timeout: int = 30, allow_redirects: bool = True):
            response = super().get(url, timeout, allow_redirects)
            if url.endswith("/api/ready"):
                return response
            response.history = [
                FakeResponse(302, headers={"Location": "/play?token=must-not-survive"}, url=url),
                FakeResponse(302, headers={"Location": f"/mobile/{response.url.rsplit('/', 1)[-1]}"}, url=url),
            ]
            return response

    payload = module.live_projection("https://example.test", session=LeakyHistorySession())

    assert payload["status"] == "fail"
    assert "gm_secret_extra (/play?role=gm&secret=must-not-survive&extra=1): exactlyOneRedirect failed" in payload["failures"]
    assert "gm_secret_extra (/play?role=gm&secret=must-not-survive&extra=1): cleanRedirectLocations failed" in payload["failures"]

    def test_verifier_fails_when_opt_in_required_ledger_stream_leaks_world_payload(self) -> None:
        class DriftedSession(_FakeSession):
            def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
                response = super().get(url, timeout=timeout, allow_redirects=allow_redirects)
                if url.endswith("/mobile/pwa/ledger.json"):
                    payload = dict(response.json())
                    payload["world"] = {"world_name": "Leaked world"}
                    payload["top_districts"] = [{"name": "Leaked district", "heat": 71}]
                    payload["continuity"] = {"turn": 7}
                    return _FakeResponse(response.url, json_data=payload, headers=response.headers)
                return response

        module = _load_module()
        stdout = io.StringIO()
        captured_payloads: list[dict] = []

        with (
            patch.object(module.requests, "Session", return_value=DriftedSession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json", side_effect=lambda _path, payload: captured_payloads.append(payload)),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.run("http://example.test")

        self.assertEqual(result, 1)
        self.assertNotIn("mobile_pwa_public_projection:ok", stdout.getvalue())
        self.assertTrue(
            any(check["id"] == "ledger_stream_opt_in_boundary_holds" and check["pass"] is False for check in captured_payloads[0]["checks"])
        )
        self.assertIn("continuity", captured_payloads[0]["ledger_stream"]["opt_in_required_leaked_keys"])
        self.assertIn("top_districts", captured_payloads[0]["ledger_stream"]["opt_in_required_leaked_keys"])
        self.assertIn("world", captured_payloads[0]["ledger_stream"]["opt_in_required_leaked_keys"])


def test_run_writes_v2_audit_without_gating_on_legacy_interactive_proof(monkeypatch) -> None:
    module = load_module()
    written: list[dict] = []
    monkeypatch.setattr(module, "source_topology", lambda source_root: {
        "contractName": module.CONTRACT_NAME,
        "mode": "source",
        "status": "pass",
        "failures": [],
    })
    monkeypatch.setattr(module, "write_audit_artifacts", lambda payload, markdown: written.append(payload))
    stdout = io.StringIO()

    with redirect_stdout(stdout):
        result = module.run(mobile_release_proof_path=Path("/stale/interactive-proof.json"))

    assert result == 0
    assert stdout.getvalue().strip() == "mobile_pwa_public_projection:ok"
    assert written[0]["legacyMobileReleaseProof"]["gating"] is False


def test_release_rehearsal_uses_only_the_canonical_mobile_pwa_browser_proof() -> None:
    rehearsal = (ROOT / "scripts" / "release_dress_rehearsal.sh").read_text(encoding="utf-8")
    matching_lines = [
        line.strip().removesuffix("\\").strip()
        for line in rehearsal.splitlines()
        if "mobile-pwa-public.spec.ts" in line
    ]

    assert matching_lines == ["tests/public/mobile-pwa-public.spec.ts"]
    assert (ROOT / "tests" / "public" / "mobile-pwa-public.spec.ts").is_file()
    assert not (ROOT / "mobile-pwa-public.spec.ts").exists()
