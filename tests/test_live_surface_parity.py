from __future__ import annotations

import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_live_surface_parity.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_live_surface_parity", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output_dir = Path(tempfile.mkdtemp(prefix="chummer-live-surface-parity-test-"))
    module.OUTPUT_PATH = output_dir / "LIVE_SURFACE_PARITY.generated.json"
    return module


class _SurfaceHandler(BaseHTTPRequestHandler):
    billing_mode = "configured"
    downloads_mode = "review"
    mobile_gm_missing_heading = False
    guest_play_public = False
    release_status = "published"
    release_version = "run-test"
    release_channel = "public_stable"
    release_supportability_state = "review_required"
    release_rollout_state = "coverage_incomplete"
    public_install_count = 1

    def do_GET(self):  # noqa: N802
        if self.path == "/downloads/RELEASE_CHANNEL.generated.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "status": self.release_status,
                        "version": self.release_version,
                        "channel": self.release_channel,
                        "supportabilityState": self.release_supportability_state,
                        "rolloutState": self.release_rollout_state,
                        "publicTrustMetrics": {
                            "adoptionHealth": {
                                "publicInstallCount": self.public_install_count,
                            }
                        },
                    }
                ).encode("utf-8")
            )
            return

        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            play_control = (
                b"<a class=\"site-account-menu__link site-open-chummer-menu__button\" href=\"/mobile/player\" data-analytics-label=\"Play\">Play</a>"
                if self.guest_play_public
                else b"<button class=\"site-account-menu__button site-open-chummer-menu__button site-open-chummer-menu__button--disabled\" type=\"button\" disabled aria-disabled=\"true\" data-disabled-target=\"/mobile/player\" data-sign-in-href=\"/login?next=%2Fmobile%2Fplayer\" data-analytics-label=\"Play\">Play</button>"
            )
            installer_copy = (
                b"No public installer right now.</p><p>Current public lane: Downloads paused."
                if self.public_install_count <= 0
                else b"Current public installer: Windows."
            )
            self.wfile.write(
                b"<html><body>"
                b"A Shadowrun character manager for clean sheets and faster tables."
                b"<a>Download Chummer</a><p>" + installer_copy + b"</p><a>Help</a><a>Status</a>"
                b"<details class=\"site-account-menu site-open-chummer-menu\">"
                b"<summary><span>Open Chummer</span></summary>"
                b"<div class=\"site-account-menu__panel\">"
                b"<button class=\"site-account-menu__button site-open-chummer-menu__button site-open-chummer-menu__button--disabled\" type=\"button\" disabled aria-disabled=\"true\" data-disabled-target=\"/build\" data-sign-in-href=\"/login?next=%2Fbuild\" data-analytics-label=\"Build\">Build</button>"
                + play_control +
                b"<a href=\"/login?next=%2Faccount%2Faccess\" data-analytics-label=\"Sign in first\">Sign in first</a>"
                b"</div></details>"
                b"</body></html>"
            )
            return

        if self.path == "/downloads":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if self.downloads_mode == "paused":
                self.wfile.write(
                    b"<html><body>"
                    b"Downloads Chummer selects the best installer when it can. Current public installer "
                    b"No build is available right now Help"
                    b'<a class="inline-link" href="/now">Release notes and known issues</a>'
                    b"</body></html>"
                )
            elif self.downloads_mode == "gold":
                self.wfile.write(
                    b"<html><body>"
                    b"Downloads Chummer selects the best installer when it can. Stable Stable release. Nightly Build from source Download script"
                    b'<a class="inline-link" href="/now">Release notes and known issues</a>'
                    b"</body></html>"
                )
            else:
                self.wfile.write(
                    b"<html><body>"
                    b"Downloads Chummer selects the best installer when it can. No Stable build on this shelf. Nightly Preview build. Review required. Build from source Download script"
                    b'<a class="inline-link" href="/now">Release notes and known issues</a>'
                    b"</body></html>"
                )
            return

        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            stable_lane_published = (
                self.release_channel in {"public_stable", "stable", "docker"}
                or self.release_rollout_state == "public_stable"
            )
            review_required = (
                not stable_lane_published
                or self.release_status != "published"
                or self.release_supportability_state != "gold_supported"
                or self.release_rollout_state in {"coverage_incomplete", "release_review_required", "desktop_polish_needed", "revoked"}
            )
            heading = (
                b"Downloads paused"
                if self.public_install_count <= 0
                else b"Preview downloads"
                if review_required
                else b"Stable downloads"
            )
            status_line = (
                b"Downloads are paused."
                if self.public_install_count <= 0
                else b"Windows and Linux downloads are live. Stable is still unavailable."
                if review_required
                else b"Windows and Linux downloads are live."
            )
            self.wfile.write(
                b"<html><head><title>Status \xc2\xb7 Chummer</title></head><body>"
                b"<section class=\"minimal-page-hero minimal-status-pill\">"
                b"<p>Now</p><h1>" + heading + b"</h1><p>" + status_line + b"</p>"
                b"<a href=\"/downloads\" data-analytics-surface=\"status_decision\">Downloads</a>"
                b"<a href=\"/help\" data-analytics-surface=\"status_decision\">Help</a>"
                b"</section>"
                b"</body></html>"
            )
            return

        if self.path.startswith("/login"):
            billing_login = "next=%2Faccount%2Fbilling" in self.path or "next=/account/billing" in self.path
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                (
                    b"<html><body>"
                    + (
                        b"Supporter Google first. Billing stays attached after that step. After this step, Chummer returns to billing. Continue with Google"
                        if billing_login
                        else b"Open Chummer Email first. Google if you prefer. Continue with email Continue with Google"
                    )
                    + b"</body></html>"
                )
            )
            return

        if self.path == "/account/billing":
            if self.billing_mode == "placeholder":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<html><body>"
                    b"Membership Supporter is not open right now. Continue with email"
                    b"</body></html>"
                )
            else:
                self.send_response(302)
                self.send_header("Location", "/login?next=%2Faccount%2Fbilling")
                self.end_headers()
            return

        if self.path == "/partizipate":
            self.send_response(302)
            self.send_header("Location", "/participate")
            self.end_headers()
            return

        if self.path == "/participate":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"<title>Participate \xc2\xb7 Chummer</title>"
                b"<meta name=\"description\" content=\"Participate\">"
                b"<h1>Participate</h1>"
                b"<iframe src=\"/participate/board?embed=1\" data-chummer-participate-frame></iframe>"
                b"</body></html>"
            )
            return

        if self.path == "/participate/board":
            self.send_response(302)
            self.send_header("Location", "/participate")
            self.end_headers()
            return

        if self.path == "/roadmap":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"<title>Roadmap \xc2\xb7 Chummer</title>"
                b"<h1>Roadmap</h1>"
                b"</body></html>"
            )
            return

        if self.path == "/roadmap/board":
            self.send_response(302)
            self.send_header("Location", "/participate")
            self.end_headers()
            return

        mobile_roles = {
            "/mobile": ("Player", "Claimed player actor"),
            "/mobile/player": ("Player", "Claimed player actor"),
            "/mobile/gm": ("GameMaster", "GM focus actor"),
            "/mobile/observer": ("Observer", "Observer mirror"),
        }
        if self.path in mobile_roles:
            role, summary = mobile_roles[self.path]
            if self.path == "/mobile/gm" and self.mobile_gm_missing_heading:
                summary = "Mobile shell"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                (
                    "<html><head>"
                    "<title>Chummer Mobile Turn Companion</title>"
                    "<script src=\"/mobile-turn-companion.js\"></script>"
                    "</head><body>"
                    f"<main data-turn-root data-role=\"{role}\">"
                    "<p>Device posture</p>"
                    "<p>Live-session turn companion</p>"
                    f"<h1>{summary} on scene-main</h1>"
                    "<a>Player</a>"
                    "<a>GM</a>"
                    "<a>Observer</a>"
                    "</main>"
                    "</body></html>"
                ).encode("utf-8")
            )
            return

        if self.path == "/play":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"<h1>Player entry</h1>"
                b"<a>Open Chummer</a>"
                b"<button>Install this app</button>"
                b"<h2>Black Ledger live tracker</h2>"
                b"<span data-pwa-ledger-status>Checking</span>"
                b"<span data-pwa-ledger-summary>Waiting for live board stream data.</span>"
                b"<p>Player, GM, and observer entry points meet in one shell.</p>"
                b"</body></html>"
            )
            return

        if self.path == "/play/continuity":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"<h1>NEXUS-PAN continuity</h1>"
                b"<p>Continuity stays cross-device, while the public page only shows safe aggregate status.</p>"
                b"<a>Open continuity history</a>"
                b"</body></html>"
            )
            return

        if self.path == "/ledger":
            self.send_response(302)
            self.send_header("Location", "/ledger/map")
            self.end_headers()
            return

        if self.path == "/ledger/map":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body>Black Ledger command map Command map</body></html>")
            return

        if self.path == "/ledger/newsroom":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body>Black Ledger Newsroom Transcript Published:</body></html>")
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A003
        return


class LiveSurfaceParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), _SurfaceHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self) -> None:
        _SurfaceHandler.billing_mode = "configured"
        _SurfaceHandler.downloads_mode = "review"
        _SurfaceHandler.mobile_gm_missing_heading = False
        _SurfaceHandler.guest_play_public = False
        _SurfaceHandler.release_status = "published"
        _SurfaceHandler.release_version = "run-test"
        _SurfaceHandler.release_channel = "public_stable"
        _SurfaceHandler.release_supportability_state = "review_required"
        _SurfaceHandler.release_rollout_state = "coverage_incomplete"
        _SurfaceHandler.public_install_count = 1

    def test_verify_requires_public_participate_surfaces(self) -> None:
        module = load_module()

        payload = module.verify(self.base_url)

        self.assertEqual("pass", payload["status"])

        participate = next(item for item in payload["results"] if item["path"] == "/participate")
        self.assertEqual(200, participate["status_code"])
        self.assertFalse(participate["cross_origin_redirect"])
        self.assertEqual([], participate["redirect_chain"])
        self.assertEqual(f"{self.base_url}/participate", participate["final_url"])
        self.assertEqual([], participate["missing_required_texts"])
        self.assertEqual([], participate["missing_required_html_texts"])
        self.assertEqual([], participate["forbidden_html_hits"])

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG001
                return None

        typo_redirect = urllib.request.build_opener(_NoRedirect())
        try:
            response = typo_redirect.open(f"{self.base_url}/partizipate", timeout=10)
        except urllib.error.HTTPError as exc:
            status_code = exc.code
            location = exc.headers.get("Location")
        else:
            status_code = getattr(response, "status", 200)
            location = response.headers.get("Location")
        self.assertEqual(302, status_code)
        self.assertEqual("/participate", location)

        board = next(item for item in payload["results"] if item["path"] == "/participate/board")
        self.assertEqual(200, board["status_code"])
        self.assertFalse(board["cross_origin_redirect"])
        self.assertEqual(f"{self.base_url}/participate", board["final_url"])
        self.assertEqual([f"{self.base_url}/participate"], board["redirect_chain"])
        self.assertEqual([], board["missing_required_texts"])
        self.assertEqual([], board["forbidden_hits"])

        status = next(item for item in payload["results"] if item["path"] == "/status")
        self.assertEqual(200, status["status_code"])
        self.assertEqual(f"{self.base_url}/status", status["final_url"])
        self.assertFalse(status["cross_origin_redirect"])
        self.assertEqual([], status["redirect_chain"])
        self.assertIsNone(status["required_final_url_prefix"])
        self.assertEqual([], status["missing_required_texts"])
        self.assertEqual([], status["missing_required_any_texts"])
        self.assertEqual([], status["missing_required_html_texts"])
        self.assertEqual([], status["forbidden_hits"])
        self.assertIn("Release notes", status["forbidden_texts"])

    def test_verify_derives_review_download_copy_from_release_manifest(self) -> None:
        module = load_module()

        payload = module.verify(self.base_url)

        self.assertEqual("pass", payload["status"])
        self.assertTrue(payload["release_posture"]["review_required"])
        self.assertEqual("review_required", payload["release_posture"]["supportability_state"])
        downloads = next(item for item in payload["results"] if item["path"] == "/downloads")
        self.assertIn("No Stable build on this shelf.", downloads["required_texts"])
        self.assertIn("Preview build. Review required.", downloads["required_texts"])
        self.assertIn("Stable release.", downloads["forbidden_texts"])
        self.assertIn(
            '<a class="inline-link" href="/now">Release notes and known issues</a>',
            downloads["required_html_texts"],
        )
        self.assertEqual([], downloads["missing_required_html_texts"])
        self.assertNotIn("Release notes", downloads["forbidden_texts"])

    def test_verify_accepts_truthful_paused_surfaces_when_manifest_has_no_public_installer(self) -> None:
        module = load_module()
        _SurfaceHandler.public_install_count = 0
        _SurfaceHandler.downloads_mode = "paused"

        payload = module.verify(self.base_url)

        self.assertEqual("pass", payload["status"], payload["failures"])
        self.assertTrue(payload["release_posture"]["downloads_paused"])
        self.assertFalse(payload["release_posture"]["public_installer_available"])
        home = next(item for item in payload["results"] if item["path"] == "/")
        downloads = next(item for item in payload["results"] if item["path"] == "/downloads")
        status = next(item for item in payload["results"] if item["path"] == "/status")
        self.assertIn("No public installer right now.", home["required_texts"])
        self.assertIn("Current public lane: Downloads paused.", home["required_texts"])
        self.assertIn("No build is available right now", downloads["required_texts"])
        self.assertIn("Build from source", downloads["forbidden_texts"])
        self.assertIn("Downloads paused", status["required_texts"])

    def test_verify_rejects_download_rails_when_manifest_has_no_public_installer(self) -> None:
        module = load_module()
        _SurfaceHandler.public_install_count = 0
        _SurfaceHandler.downloads_mode = "review"

        payload = module.verify(self.base_url)

        self.assertEqual("fail", payload["status"])
        downloads = next(item for item in payload["results"] if item["path"] == "/downloads")
        self.assertIn("No build is available right now", downloads["missing_required_texts"])
        self.assertIn("Build from source", downloads["forbidden_hits"])
        self.assertIn("Preview build. Review required.", downloads["forbidden_hits"])

    def test_verify_records_expected_release_channel_match_when_receipt_is_supplied(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="live-surface-release-channel-") as temp_dir:
            receipt = Path(temp_dir) / "RELEASE_CHANNEL.generated.json"
            receipt.write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "public_stable",
                        "supportabilityState": "review_required",
                        "rolloutState": "coverage_incomplete",
                    }
                ),
                encoding="utf-8",
            )

            payload = module.verify(self.base_url, release_channel_receipt=receipt)

        self.assertEqual("pass", payload["status"], payload["failures"])
        self.assertEqual([], payload["release_posture"]["expected_failures"])
        self.assertTrue(payload["release_posture"]["version_matches_expected"])
        self.assertTrue(payload["release_posture"]["supportability_matches_expected"])
        self.assertTrue(payload["release_posture"]["rollout_matches_expected"])

    def test_verify_fails_when_live_release_manifest_mismatches_expected_release_channel(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="live-surface-release-channel-mismatch-") as temp_dir:
            receipt = Path(temp_dir) / "RELEASE_CHANNEL.generated.json"
            receipt.write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "public_stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )

            payload = module.verify(self.base_url, release_channel_receipt=receipt)

        self.assertEqual("fail", payload["status"])
        self.assertFalse(payload["release_posture"]["supportability_matches_expected"])
        self.assertFalse(payload["release_posture"]["rollout_matches_expected"])
        self.assertIn(
            "live release manifest supportabilityState does not match expected release channel",
            payload["failures"],
        )
        self.assertIn(
            "live release manifest rolloutState does not match expected release channel",
            payload["failures"],
        )

    def test_verify_allows_stable_copy_only_when_release_manifest_is_gold_supported(self) -> None:
        module = load_module()
        _SurfaceHandler.downloads_mode = "gold"
        _SurfaceHandler.release_supportability_state = "gold_supported"
        _SurfaceHandler.release_rollout_state = "public_stable"

        payload = module.verify(self.base_url)

        self.assertEqual("pass", payload["status"], payload["failures"])
        self.assertFalse(payload["release_posture"]["review_required"])
        downloads = next(item for item in payload["results"] if item["path"] == "/downloads")
        self.assertIn("Stable release.", downloads["required_texts"])
        self.assertIn("No Stable build on this shelf.", downloads["forbidden_texts"])

    def test_verify_allows_stable_copy_when_docker_channel_is_gold_supported(self) -> None:
        module = load_module()
        _SurfaceHandler.downloads_mode = "gold"
        _SurfaceHandler.release_channel = "docker"
        _SurfaceHandler.release_supportability_state = "gold_supported"
        _SurfaceHandler.release_rollout_state = "public_stable"

        payload = module.verify(self.base_url)

        self.assertEqual("pass", payload["status"], payload["failures"])
        self.assertFalse(payload["release_posture"]["review_required"])
        downloads = next(item for item in payload["results"] if item["path"] == "/downloads")
        self.assertIn("Stable release.", downloads["required_texts"])
        self.assertIn("No Stable build on this shelf.", downloads["forbidden_texts"])

    def test_verify_rejects_stable_copy_while_release_manifest_requires_review(self) -> None:
        module = load_module()
        _SurfaceHandler.downloads_mode = "gold"

        payload = module.verify(self.base_url)

        self.assertEqual("fail", payload["status"])
        downloads = next(item for item in payload["results"] if item["path"] == "/downloads")
        self.assertIn("No Stable build on this shelf.", downloads["missing_required_texts"])
        self.assertIn("Preview build. Review required.", downloads["missing_required_texts"])
        self.assertIn("Stable release.", downloads["forbidden_hits"])
        self.assertIn("/downloads: contains forbidden text: Stable release.", payload["failures"])

    def test_verify_keeps_preview_posture_when_preview_channel_is_gold_supported_but_not_stable_lane(self) -> None:
        module = load_module()
        _SurfaceHandler.release_channel = "preview"
        _SurfaceHandler.release_supportability_state = "gold_supported"
        _SurfaceHandler.release_rollout_state = "promoted_preview"

        payload = module.verify(self.base_url)

        self.assertEqual("pass", payload["status"], payload["failures"])
        self.assertTrue(payload["release_posture"]["review_required"])
        downloads = next(item for item in payload["results"] if item["path"] == "/downloads")
        self.assertIn("No Stable build on this shelf.", downloads["required_texts"])
        self.assertIn("Preview build. Review required.", downloads["required_texts"])
        self.assertIn("Stable release.", downloads["forbidden_texts"])

    def test_verify_rejects_public_frontdoor_play_link_for_signed_out_homepage(self) -> None:
        module = load_module()
        _SurfaceHandler.guest_play_public = True

        payload = module.verify(self.base_url)

        self.assertEqual("fail", payload["status"])
        home = next(item for item in payload["results"] if item["path"] == "/")
        self.assertIn("data-disabled-target=\"/mobile/player\"", home["missing_required_html_texts"])
        self.assertIn("data-sign-in-href=\"/login?next=%2Fmobile%2Fplayer\"", home["missing_required_html_texts"])
        self.assertIn("site-open-chummer-menu__button\" href=\"/mobile/player\"", home["forbidden_html_hits"])
        self.assertIn(
            "/: contains forbidden html text: site-open-chummer-menu__button\" href=\"/mobile/player\"",
            payload["failures"],
        )

    def test_verify_accepts_minimal_roadmap_and_redirects_board_to_participate(self) -> None:
        module = load_module()

        payload = module.verify(self.base_url)

        self.assertEqual("pass", payload["status"])
        roadmap = next(item for item in payload["results"] if item["path"] == "/roadmap")
        self.assertEqual([], roadmap["missing_required_texts"])
        self.assertEqual([], roadmap["missing_required_any_texts"])

        roadmap = next(item for item in payload["results"] if item["path"] == "/roadmap")
        self.assertEqual(200, roadmap["status_code"])
        self.assertFalse(roadmap["cross_origin_redirect"])
        self.assertEqual([], roadmap["missing_required_texts"])
        self.assertEqual([], roadmap["forbidden_hits"])

        roadmap_board = next(item for item in payload["results"] if item["path"] == "/roadmap/board")
        self.assertEqual(200, roadmap_board["status_code"])
        self.assertFalse(roadmap_board["cross_origin_redirect"])
        self.assertEqual(f"{self.base_url}/participate", roadmap_board["final_url"])
        self.assertEqual([f"{self.base_url}/participate"], roadmap_board["redirect_chain"])
        self.assertEqual([], roadmap_board["missing_required_texts"])
        self.assertEqual([], roadmap_board["forbidden_hits"])

    def test_verify_requires_participate_embedded_board_shell(self) -> None:
        module = load_module()
        participate_surface = next(item for item in module.SURFACES if item["path"] == "/participate")

        self.assertIn("Participate", participate_surface["required_texts"])
        self.assertNotIn("What should Chummer do next?", participate_surface["required_texts"])
        self.assertNotIn("Current requests", participate_surface["required_texts"])
        self.assertIn("<title>Participate · Chummer</title>", participate_surface["required_html_texts"])
        self.assertIn("data-chummer-participate-frame", participate_surface["required_html_texts"])
        self.assertIn("/participate/board?embed=1", participate_surface["required_html_texts"])
        self.assertNotIn("Board is live.", participate_surface["required_texts"])
        self.assertIn("participate-preview-card", participate_surface["forbidden_html_texts"])
        self.assertIn("data-chummer-board-skin", participate_surface["forbidden_html_texts"])

    def test_verify_blocks_provider_chrome_on_participate_board(self) -> None:
        module = load_module()
        board_surface = next(item for item in module.SURFACES if item["path"] == "/participate/board")

        self.assertIn("ProductLift", board_surface["forbidden_texts"])
        self.assertIn("Log in", board_surface["forbidden_texts"])
        self.assertIn("Sign up", board_surface["forbidden_texts"])
        self.assertIn("Search", board_surface["forbidden_texts"])
        self.assertIn("Ctrl K", board_surface["forbidden_texts"])
        self.assertIn("×", board_surface["forbidden_texts"])
        self.assertIn("Could not load posts", board_surface["forbidden_texts"])
        self.assertNotIn("Board is live.", board_surface["required_texts"])
        self.assertNotIn("Current requests", board_surface["required_texts"])
        self.assertIn("Participate", board_surface["required_texts"])
        self.assertIn("<title>Participate · Chummer</title>", board_surface["required_html_texts"])
        self.assertIn("data-chummer-board-skin", board_surface["forbidden_html_texts"])

    def test_verify_requires_mobile_role_and_continuity_surfaces(self) -> None:
        module = load_module()

        payload = module.verify(self.base_url)

        self.assertEqual("pass", payload["status"])
        by_path = {item["path"]: item for item in payload["results"]}
        for path, role_marker in {
            "/mobile": "Claimed player actor",
            "/mobile/player": "Claimed player actor",
            "/mobile/gm": "GM focus actor",
            "/mobile/observer": "Observer mirror",
            "/play": "Player entry",
            "/play/continuity": "NEXUS-PAN continuity",
        }.items():
            self.assertIn(path, by_path)
            self.assertEqual(200, by_path[path]["status_code"])
            self.assertIn(role_marker, by_path[path]["required_texts"])
            self.assertEqual([], by_path[path]["missing_required_texts"])

        self.assertIn("data-turn-root", by_path["/mobile/gm"]["required_html_texts"])
        self.assertIn("data-role=\"GameMaster\"", by_path["/mobile/gm"]["required_html_texts"])
        self.assertEqual([], by_path["/mobile/gm"]["missing_required_html_texts"])

    def test_verify_fails_when_mobile_gm_role_surface_loses_role_heading(self) -> None:
        module = load_module()
        _SurfaceHandler.mobile_gm_missing_heading = True

        payload = module.verify(self.base_url)

        self.assertEqual("fail", payload["status"])
        gm = next(item for item in payload["results"] if item["path"] == "/mobile/gm")
        self.assertIn("GM focus actor", gm["missing_required_texts"])
        self.assertIn("/mobile/gm: missing required text: GM focus actor", payload["failures"])

    def test_verify_records_fetch_error_when_surface_has_no_http_status(self) -> None:
        module = load_module()
        original_fetch = module.fetch

        def fake_fetch(url: str, base_url: str):
            if url.endswith("/ledger/newsroom"):
                return None, "TimeoutError: timed out", url, None, [], "TimeoutError: timed out"
            return original_fetch(url, base_url)

        with mock.patch.object(module, "fetch", side_effect=fake_fetch):
            payload = module.verify(self.base_url)

        self.assertEqual("fail", payload["status"])
        newsroom = next(item for item in payload["results"] if item["path"] == "/ledger/newsroom")
        self.assertEqual("TimeoutError: timed out", newsroom["fetch_error"])
        self.assertIn(
            "/ledger/newsroom: expected 200, got None (TimeoutError: timed out)",
            payload["failures"],
        )

    def test_fetch_retries_timeout_then_succeeds(self) -> None:
        module = load_module()
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.status = 200
        response.read.return_value = b"<html><body>ok</body></html>"
        response.geturl.return_value = "https://example.test/mobile/player"
        response.headers.get.return_value = None
        opener = mock.Mock()
        opener.open.side_effect = [TimeoutError("timed out"), response]

        with (
            mock.patch.object(module.urllib.request, "build_opener", return_value=opener),
            mock.patch.object(module.time, "sleep") as sleep,
        ):
            status_code, body, final_url, redirect_location, redirect_chain, fetch_error = module.fetch(
                "https://example.test/mobile/player",
                "https://example.test",
            )

        self.assertEqual(200, status_code)
        self.assertEqual("<html><body>ok</body></html>", body)
        self.assertEqual("https://example.test/mobile/player", final_url)
        self.assertIsNone(redirect_location)
        self.assertEqual([], redirect_chain)
        self.assertIsNone(fetch_error)
        self.assertEqual(2, opener.open.call_count)
        sleep.assert_called_once()

    def test_verify_supports_guest_billing_sign_in_handoff_when_live_checkout_is_required(self) -> None:
        module = load_module()
        _SurfaceHandler.billing_mode = "configured"
        with mock.patch.dict("os.environ", {"CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT": "1"}, clear=False):
            payload = module.verify(self.base_url)

        self.assertEqual("pass", payload["status"])
        self.assertTrue(payload["require_brilliant_directories_checkout"])
        billing = next(item for item in payload["results"] if item["path"] == "/account/billing")
        self.assertEqual("/login", urllib.parse.urlparse(billing["final_url"]).path)
        self.assertEqual([], billing["missing_required_texts"])
        self.assertEqual([], billing["missing_required_any_texts"])
        self.assertEqual([], billing["forbidden_hits"])

    def test_verify_rejects_placeholder_billing_surface_when_live_checkout_is_required(self) -> None:
        module = load_module()
        _SurfaceHandler.billing_mode = "placeholder"
        with mock.patch.dict("os.environ", {"CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT": "1"}, clear=False):
            payload = module.verify(self.base_url)

        self.assertEqual("fail", payload["status"])
        billing = next(item for item in payload["results"] if item["path"] == "/account/billing")
        self.assertIn("Google first. Billing stays attached after that step.", billing["missing_required_any_texts"])
        self.assertIn("Supporter is not open right now.", billing["forbidden_hits"])

    def test_public_chummer_run_base_requires_billing_checkout_without_env_flag(self) -> None:
        module = load_module()

        self.assertTrue(module.is_public_chummer_run_base(urllib.parse.urlparse("https://chummer.run")))
        self.assertTrue(module.is_public_chummer_run_base(urllib.parse.urlparse("https://www.chummer.run")))
        self.assertFalse(module.is_public_chummer_run_base(urllib.parse.urlparse(self.base_url)))
        self.assertFalse(module.is_public_chummer_run_base(urllib.parse.urlparse("http://chummer.run")))

    def test_mainline_payload_remains_json_serializable(self) -> None:
        module = load_module()

        payload = module.verify(self.base_url)

        serialized = json.dumps(payload)
        self.assertIn("LIVE_SURFACE_PARITY_READY", serialized)

    def test_verify_can_write_to_explicit_output_path_for_read_only_audits(self) -> None:
        module = load_module()
        output_path = Path(tempfile.mkdtemp(prefix="chummer-live-surface-explicit-")) / "live-surface.json"

        payload = module.verify(self.base_url, output_path=output_path)

        self.assertEqual("pass", payload["status"])
        self.assertTrue(output_path.is_file())
        written = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual("chummer.live_surface_parity", written["contract_name"])
        self.assertEqual("pass", written["status"])


if __name__ == "__main__":
    unittest.main()
