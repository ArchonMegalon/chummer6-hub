from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_mobile_pwa_public_projection.py"
DESIGN_SPEC_PATH = REPO_ROOT.parent / "chummer-design" / "products" / "chummer" / "MOBILE_PWA_PRODUCT_SPEC.md"


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
                    '<a class="site-open-chummer-menu__button" href="/build">Build</a>'
                    '<a class="site-open-chummer-menu__button" href="/play">Play</a>'
                    "</div></details>"
                ),
            )
        if url.endswith("/build"):
            return _FakeResponse(
                "http://example.test/app?command=character_roster",
                text="<main class=\"browser-preview-shell\"><h1>Character Roster</h1><p>Chummer Online</p></main>",
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
                    "legal_posture": "Public lane stays aggregate only. No private run table state is published.",
                    "opt_in_route": "/account",
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
    spec.loader.exec_module(module)
    return module


class MobilePwaPublicProjectionTests(unittest.TestCase):
    def test_design_spec_tracks_live_pwa_projection_contract(self) -> None:
        text = DESIGN_SPEC_PATH.read_text(encoding="utf-8")

        for required in (
            "during-play companion surface",
            "`/mobile` is the canonical PWA start URL",
            "`/pwa` redirects to",
            "`/play` is the shared play shell",
            "`/player`, `/gm`, `/observer`, and",
            "`/mobile/pwa/ledger.json`",
            "`mode: mobile_pwa_living_world`",
            "`updates_route: /mobile/pwa/ledger.json`",
            "`opt_in_required`, `no_world_data`,",
            "`live`, and `world_not_followed`",
            "no-store caching and vary by",
            "`Cookie` and `Authorization`",
            "must never be pre-cached",
            "`/play/continuity/history` or `/play/continuity/receipts`",
            "scripts/verify_mobile_pwa_public_projection.py --base-url https://chummer.run",
            "tests/public/mobile-pwa-public.spec.ts",
            "tests/public/pwa-installability.spec.ts",
            "tests/public/pwa-offline-cache.spec.ts",
            "not be described as a complete mobile character builder",
        ):
            self.assertIn(required, text)

        self.assertNotIn("preview shell", text)
        self.assertNotIn("Gate `gate-mobile-pwa` includes", text)

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

    def test_verifier_fails_when_role_route_redirect_drifts(self) -> None:
        class DriftedSession(_FakeSession):
            def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
                if url.endswith("/gm"):
                    return _FakeResponse("http://example.test/play")
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
                    return _FakeResponse(response.url, text=response.text.replace('href="/play"', 'href="/account"', 1))
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
        self.assertIn('href="/play"', captured_payloads[0]["public_entry"]["home_open_chummer_missing_markers"])

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

    def test_verifier_fails_when_mobile_page_drops_service_worker_registration(self) -> None:
        class DriftedSession(_FakeSession):
            def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
                response = super().get(url, timeout=timeout, allow_redirects=allow_redirects)
                if url.endswith("/mobile"):
                    return _FakeResponse(
                        response.url,
                        text=response.text.replace('serviceWorker.register("/service-worker.js?v=test")', "console.log('no sw')", 1),
                    )
                return response

        module = _load_module()
        stdout = io.StringIO()

        with (
            patch.object(module.requests, "Session", return_value=DriftedSession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json"),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.run("http://example.test")

        self.assertEqual(result, 1)
        self.assertNotIn("mobile_pwa_public_projection:ok", stdout.getvalue())

    def test_verifier_fails_when_manifest_id_drifts(self) -> None:
        class DriftedSession(_FakeSession):
            def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
                response = super().get(url, timeout=timeout, allow_redirects=allow_redirects)
                if url.endswith("/manifest.json"):
                    manifest = dict(response.json())
                    manifest["id"] = "/play"
                    return _FakeResponse(response.url, json_data=manifest)
                return response

        module = _load_module()
        stdout = io.StringIO()

        with (
            patch.object(module.requests, "Session", return_value=DriftedSession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json"),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.run("http://example.test")

        self.assertEqual(result, 1)
        self.assertNotIn("mobile_pwa_public_projection:ok", stdout.getvalue())

    def test_verifier_fails_when_service_worker_drops_required_shell_cache_path(self) -> None:
        class DriftedSession(_FakeSession):
            def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
                response = super().get(url, timeout=timeout, allow_redirects=allow_redirects)
                if "/service-worker.js" in url:
                    return _FakeResponse(
                        response.url,
                        text=response.text.replace('"/play/continuity", ', "", 1),
                    )
                return response

        module = _load_module()
        stdout = io.StringIO()

        with (
            patch.object(module.requests, "Session", return_value=DriftedSession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json"),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.run("http://example.test")

        self.assertEqual(result, 1)
        self.assertNotIn("mobile_pwa_public_projection:ok", stdout.getvalue())

    def test_verifier_fails_when_service_worker_allows_personalized_ledger_stream_cache(self) -> None:
        class DriftedSession(_FakeSession):
            def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
                response = super().get(url, timeout=timeout, allow_redirects=allow_redirects)
                if "/service-worker.js" in url:
                    return _FakeResponse(
                        response.url,
                        text=response.text.replace('"/mobile/pwa/ledger.json"', "", 1),
                    )
                return response

        module = _load_module()
        stdout = io.StringIO()

        with (
            patch.object(module.requests, "Session", return_value=DriftedSession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json"),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.run("http://example.test")

        self.assertEqual(result, 1)
        self.assertNotIn("mobile_pwa_public_projection:ok", stdout.getvalue())

    def test_verifier_fails_when_service_worker_drops_notification_route_bounds(self) -> None:
        class DriftedSession(_FakeSession):
            def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
                response = super().get(url, timeout=timeout, allow_redirects=allow_redirects)
                if "/service-worker.js" in url:
                    return _FakeResponse(
                        response.url,
                        text=response.text.replace("const NOTIFICATION_ROUTE_PATHS", "const DROPPED_NOTIFICATION_ROUTE_PATHS", 1),
                    )
                return response

        module = _load_module()
        stdout = io.StringIO()

        with (
            patch.object(module.requests, "Session", return_value=DriftedSession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json"),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.run("http://example.test")

        self.assertEqual(result, 1)
        self.assertNotIn("mobile_pwa_public_projection:ok", stdout.getvalue())

    def test_verifier_fails_when_personalized_ledger_stream_drops_no_store_headers(self) -> None:
        class DriftedSession(_FakeSession):
            def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
                response = super().get(url, timeout=timeout, allow_redirects=allow_redirects)
                if url.endswith("/mobile/pwa/ledger.json"):
                    return _FakeResponse(response.url, json_data=response.json(), headers={"Cache-Control": "public, max-age=60"})
                return response

        module = _load_module()
        stdout = io.StringIO()

        with (
            patch.object(module.requests, "Session", return_value=DriftedSession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json"),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.run("http://example.test")

        self.assertEqual(result, 1)
        self.assertNotIn("mobile_pwa_public_projection:ok", stdout.getvalue())

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


if __name__ == "__main__":
    unittest.main()
