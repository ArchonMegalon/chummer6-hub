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
REPO_ROOT = SCRIPT_PATH.parents[1]


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
    guest_play_public = True
    release_status = "published"
    release_version = "run-test"
    release_channel = "public_stable"
    release_supportability_state = "review_required"
    release_rollout_state = "coverage_incomplete"
    public_install_count = 1
    public_download_profile = False

    def do_GET(self):  # noqa: N802
        if self.path == "/downloads/RELEASE_CHANNEL.generated.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            payload = {
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
            if self.public_download_profile:
                payload["artifacts"] = [
                    {
                        "id": "avalonia-win-x64-installer",
                        "kind": "installer",
                        "installAccessClass": "open_public",
                        "downloadUrl": "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                    }
                ]
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if self.public_download_profile:
                self.wfile.write(
                    b"<html><body>"
                    b"A Shadowrun character manager for clean sheets and faster tables."
                    b"<a>Download Chummer</a>"
                    b"<p>Listed for review: Windows. Availability is not asserted.</p>"
                    b"<p>Current public lane: Preview. Review required.</p>"
                    b"<a>Help</a>"
                    b"<a href=\"/build\" data-public-install-handoff=\"true\">Build</a>"
                    b"<a href=\"/mobile/player\" data-public-install-handoff=\"true\">Play</a>"
                    b"</body></html>"
                )
                return
            handoff_controls = (
                b"<a class=\"site-account-menu__link site-open-chummer-menu__button\" href=\"/build\" data-public-install-handoff=\"true\" data-analytics-label=\"Build\">Build</a>"
                b"<a class=\"site-account-menu__link site-open-chummer-menu__button\" href=\"/mobile/player\" data-public-install-handoff=\"true\" data-analytics-label=\"Play\">Play</a>"
                if self.guest_play_public
                else (
                    b"<button type=\"button\" disabled data-disabled-target=\"/build\" data-analytics-label=\"Build\">Build</button>"
                    b"<button type=\"button\" disabled data-disabled-target=\"/mobile/player\" data-analytics-label=\"Play\">Play</button>"
                )
            )
            if self.public_install_count <= 0:
                installer_copy = b"No public installer right now.</p><p>Current public lane: Downloads paused."
            elif (
                self.release_supportability_state == "review_required"
                or self.release_rollout_state
                in {
                    "blocked",
                    "coverage_incomplete",
                    "desktop_polish_needed",
                    "public_release_review_required",
                    "release_review_required",
                }
            ):
                installer_copy = (
                    b"Listed for review: Windows. Availability is not asserted.</p>"
                    b"<p>Current public lane: Preview. Review required."
                )
            elif (
                self.release_supportability_state == "gold_supported"
                and self.release_rollout_state == "public_stable"
                and self.release_channel in {"public_stable", "stable", "docker"}
            ):
                installer_copy = b"Current public installer: Windows.</p><p>Current public lane: Stable."
            else:
                installer_copy = (
                    b"Current public installer: Windows.</p>"
                    b"<p>Current public lane: Preview. Review required."
                )
            self.wfile.write(
                b"<html><body>"
                b"A Shadowrun character manager for clean sheets and faster tables."
                b"<a>Download Chummer</a><p>" + installer_copy + b"</p><a>Help</a><a>Status</a>"
                b"<details class=\"site-account-menu site-open-chummer-menu\">"
                b"<summary><span>Open Chummer</span></summary>"
                b"<div class=\"site-account-menu__panel\">"
                + handoff_controls +
                b"<a href=\"/login?next=%2Faccount%2Faccess\" data-analytics-label=\"Sign in first\">Sign in first</a>"
                b"</div></details>"
                b"</body></html>"
            )
            return

        if self.path == "/downloads":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if self.public_download_profile:
                self.wfile.write(
                    b"<html><body>"
                    b"<h1>Downloads</h1>"
                    b"Chummer selects the best installer when it can. "
                    b"Nightly Stable Build from source Download script "
                    b"No Stable build on this shelf. Preview build. Review required."
                    b"<a class=\"inline-link\" href=\"/now\">Release notes and known issues</a>"
                    b"</body></html>"
                )
                return
            if self.downloads_mode == "paused":
                body = (
                    b"<html><body><h1>Downloads</h1>"
                    b"Chummer selects the best installer when it can. "
                    b"<h2>No public build is available right now</h2><a>Help</a>"
                    b"<a class=\"inline-link\" href=\"/now\">Release notes and known issues</a>"
                    b"</body></html>"
                )
            elif self.downloads_mode == "gold":
                body = (
                    b"<html><body><h1>Downloads</h1>"
                    b"Chummer selects the best installer when it can. "
                    b"Stable release. Nightly Stable Build from source Download script "
                    b"<a class=\"inline-link\" href=\"/now\">Release notes and known issues</a>"
                    b"</body></html>"
                )
            else:
                body = (
                    b"<html><body><h1>Downloads</h1>"
                    b"Chummer selects the best installer when it can. "
                    b"Nightly Stable Build from source Download script "
                    b"No Stable build on this shelf. Preview build. Review required. "
                    b"<a class=\"inline-link\" href=\"/now\">Release notes and known issues</a>"
                    b"</body></html>"
                )
            self.wfile.write(body)
            return

        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if self.public_download_profile:
                self.wfile.write(
                    b"<html><head><title>Status \xc2\xb7 Chummer</title></head><body>"
                    b"<section class=\"minimal-page-hero minimal-status-pill\">"
                    b"<p>Now</p><h1>Downloads under review</h1>"
                    b"<p>Windows installers remain listed for review; availability is not asserted.</p>"
                    b"<a data-analytics-surface=\"status_decision\" href=\"/downloads\">Downloads</a>"
                    b"<a href=\"/help\">Help</a>"
                    b"</section></body></html>"
                )
                return
            if self.public_install_count <= 0:
                heading = b"Downloads paused"
                summary = b"Downloads are paused."
            elif (
                self.release_supportability_state == "gold_supported"
                and self.release_rollout_state == "public_stable"
                and self.release_channel in {"public_stable", "stable", "docker"}
            ):
                heading = b"Stable downloads"
                summary = b"Windows download is live."
            elif (
                self.release_supportability_state == "review_required"
                or self.release_rollout_state
                in {
                    "blocked",
                    "coverage_incomplete",
                    "desktop_polish_needed",
                    "public_release_review_required",
                    "release_review_required",
                }
            ):
                heading = b"Downloads under review"
                summary = b"Windows installers remain listed for review; availability is not asserted."
            else:
                heading = b"Preview downloads"
                summary = b"Windows download is live."
            self.wfile.write(
                b"<html><head><title>Status \xc2\xb7 Chummer</title></head><body>"
                b"<section class=\"minimal-page-hero minimal-status-pill\">"
                b"<p>Now</p><h1>" + heading + b"</h1><p>" + summary + b"</p>"
                b"<a data-analytics-surface=\"status_decision\" href=\"/downloads\">Downloads</a>"
                b"<a href=\"/help\">Help</a>"
                b"</section></body></html>"
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
                b"<iframe src=\"/participate/board?embed=1\" referrerpolicy=\"same-origin\" data-chummer-participate-frame></iframe>"
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
            "/mobile": "player",
            "/mobile/player": "player",
            "/mobile/gm": "gm",
            "/mobile/observer": "observer",
        }
        if self.path in mobile_roles:
            role = mobile_roles[self.path]
            if self.path == "/mobile/gm" and self.mobile_gm_missing_heading:
                role = "player"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                (
                    "<html><head>"
                    "<title>Install Chummer Play</title>"
                    "<script src=\"/mobile-install-shell.js\"></script>"
                    "</head><body>"
                    "<main data-play-surface=\"install-only\" "
                    "data-live-session=\"unavailable\" "
                    "data-authority=\"none\" "
                    f"data-install-role=\"{role}\">"
                    "<p>Chummer Player · install shell</p>"
                    "<p>Public shell only</p>"
                    "<p>No table data loaded</p>"
                    "<p>No role granted</p>"
                    "<button>Install app</button>"
                    "<a>How to join</a>"
                    f"<section data-role-capabilities=\"{role}\"></section>"
                    f"<section data-role-privacy-warning=\"{role}\"></section>"
                    f"<section data-role-authority-warning=\"{role}\"></section>"
                    "</main>"
                    "</body></html>"
                ).encode("utf-8")
            )
            return

        if self.path == "/play":
            self.send_response(302)
            self.send_header("Location", "/mobile/player")
            self.end_headers()
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
        _SurfaceHandler.guest_play_public = True
        _SurfaceHandler.release_status = "published"
        _SurfaceHandler.release_version = "run-test"
        _SurfaceHandler.release_channel = "public_stable"
        _SurfaceHandler.release_supportability_state = "review_required"
        _SurfaceHandler.release_rollout_state = "coverage_incomplete"
        _SurfaceHandler.public_install_count = 1
        _SurfaceHandler.public_download_profile = False

    def test_public_download_profile_requires_anonymous_artifact_and_review_copy(self) -> None:
        module = load_module()
        _SurfaceHandler.public_download_profile = True
        _SurfaceHandler.release_channel = "preview"
        _SurfaceHandler.public_install_count = 0

        payload = module.verify(
            self.base_url,
            surface_profile=module.SURFACE_PROFILE_PUBLIC_DOWNLOAD,
        )

        self.assertEqual("pass", payload["status"], payload["failures"])
        self.assertEqual("public-download", payload["surface_profile"])
        self.assertEqual(["/", "/downloads", "/status"], [item["path"] for item in payload["results"]])
        self.assertTrue(payload["release_posture"]["public_download_artifact_available"])
        self.assertTrue(payload["release_posture"]["downloads_under_review"])
        self.assertFalse(payload["release_posture"]["downloads_paused"])
        status = next(item for item in payload["results"] if item["path"] == "/status")
        self.assertIn("Downloads under review", status["required_texts"])

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
        self.assertIn("No public build is available right now", downloads["required_texts"])
        self.assertIn("Build from source", downloads["forbidden_texts"])
        self.assertIn("Downloads paused", status["required_texts"])

    def test_verify_rejects_download_rails_when_manifest_has_no_public_installer(self) -> None:
        module = load_module()
        _SurfaceHandler.public_install_count = 0
        _SurfaceHandler.downloads_mode = "review"

        payload = module.verify(self.base_url)

        self.assertEqual("fail", payload["status"])
        downloads = next(item for item in payload["results"] if item["path"] == "/downloads")
        self.assertIn("No public build is available right now", downloads["missing_required_texts"])
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

    def test_public_download_profile_accepts_only_a_known_more_specific_review_blocker(self) -> None:
        module = load_module()
        live = {
            "status": "published",
            "version": "run-test",
            "channel": "preview",
            "supportabilityState": "review_required",
            "rolloutState": "coverage_incomplete",
        }
        expected = {
            **live,
            "rolloutState": "public_release_review_required",
        }

        public_fields, public_failures = module.release_posture_expected_failures(
            live,
            expected,
            surface_profile=module.SURFACE_PROFILE_PUBLIC_DOWNLOAD,
        )
        flagship_fields, flagship_failures = module.release_posture_expected_failures(
            live,
            expected,
            surface_profile=module.SURFACE_PROFILE_FLAGSHIP,
        )

        self.assertEqual([], public_failures)
        self.assertTrue(public_fields["monotonic_review_blocker_valid"])
        self.assertFalse(public_fields["rollout_matches_expected"])
        self.assertIn(
            "live release manifest rolloutState does not match expected release channel",
            flagship_failures,
        )
        self.assertFalse(flagship_fields["monotonic_review_blocker_valid"])

    def test_public_download_profile_accepts_evidenced_runtime_review_floor_projection(self) -> None:
        module = load_module()
        expected = {
            "status": "published",
            "version": "run-test",
            "channel": "preview",
            "supportabilityState": "review_required",
            "rolloutState": "coverage_incomplete",
            "desktopTupleCoverage": {
                "complete": False,
                "missingRequiredPlatforms": ["macos"],
            },
        }
        live = {
            **expected,
            "rolloutState": "public_release_review_required",
            "desktopTupleCoverage": {
                "complete": True,
                "missingRequiredPlatforms": [],
                "missingRequiredHeads": [],
                "missingRequiredPlatformHeadPairs": [],
                "missingRequiredPlatformHeadRidTuples": [],
            },
            "publicTrustMetrics": {
                "proofFreshness": {"status": "stale"},
                "privacyReadiness": {
                    "status": "review_required",
                    "blocksLaunch": True,
                },
            },
        }

        fields, failures = module.release_posture_expected_failures(
            live,
            expected,
            surface_profile=module.SURFACE_PROFILE_PUBLIC_DOWNLOAD,
        )

        self.assertEqual([], failures)
        self.assertFalse(fields["rollout_matches_expected"])
        self.assertTrue(fields["runtime_review_floor_projection_valid"])
        self.assertTrue(fields["rollout_compatible_with_expected"])

    def test_public_download_profile_rejects_unevidenced_runtime_review_floor_projection(self) -> None:
        module = load_module()
        expected = {
            "status": "published",
            "version": "run-test",
            "channel": "preview",
            "supportabilityState": "review_required",
            "rolloutState": "coverage_incomplete",
            "desktopTupleCoverage": {"complete": False},
        }
        live = {
            **expected,
            "rolloutState": "public_release_review_required",
            "desktopTupleCoverage": {"complete": True},
            "publicTrustMetrics": {
                "proofFreshness": {"status": "fresh"},
                "privacyReadiness": {
                    "status": "pass",
                    "blocksLaunch": False,
                },
            },
        }

        fields, failures = module.release_posture_expected_failures(
            live,
            expected,
            surface_profile=module.SURFACE_PROFILE_PUBLIC_DOWNLOAD,
        )

        self.assertFalse(fields["runtime_review_floor_projection_valid"])
        self.assertIn(
            "live release manifest rolloutState does not match expected release channel",
            failures,
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

    def test_verify_rejects_signed_in_gate_on_public_install_handoffs(self) -> None:
        module = load_module()
        _SurfaceHandler.guest_play_public = False

        payload = module.verify(self.base_url)

        self.assertEqual("fail", payload["status"])
        home = next(item for item in payload["results"] if item["path"] == "/")
        self.assertIn('href="/build"', home["missing_required_html_texts"])
        self.assertIn('href="/mobile/player"', home["missing_required_html_texts"])
        self.assertIn('data-public-install-handoff="true"', home["missing_required_html_texts"])
        self.assertIn('data-disabled-target="/build"', home["forbidden_html_hits"])
        self.assertIn('data-disabled-target="/mobile/player"', home["forbidden_html_hits"])
        self.assertIn(
            '/: contains forbidden html text: data-disabled-target="/build", data-disabled-target="/mobile/player"',
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
        self.assertIn('src="/participate/board?embed=1"', participate_surface["required_html_texts"])
        self.assertIn('referrerpolicy="same-origin"', participate_surface["required_html_texts"])
        self.assertNotIn("Board is live.", participate_surface["required_texts"])
        self.assertIn("participate-preview-card", participate_surface["forbidden_html_texts"])
        self.assertIn("data-chummer-board-skin", participate_surface["forbidden_html_texts"])
        self.assertIn("productlift.dev", participate_surface["forbidden_html_texts"])

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

    def test_verify_requires_mobile_install_boundary_and_continuity_surfaces(self) -> None:
        module = load_module()

        payload = module.verify(self.base_url)

        self.assertEqual("pass", payload["status"])
        by_path = {item["path"]: item for item in payload["results"]}
        for path, role_key in {
            "/mobile": "player",
            "/mobile/player": "player",
            "/mobile/gm": "gm",
            "/mobile/observer": "observer",
            "/play": "player",
        }.items():
            self.assertIn(path, by_path)
            self.assertEqual(200, by_path[path]["status_code"])
            self.assertIn("Public shell only", by_path[path]["required_texts"])
            self.assertIn(
                f'data-install-role="{role_key}"',
                by_path[path]["required_html_texts"],
            )
            self.assertEqual([], by_path[path]["missing_required_texts"])
            self.assertEqual([], by_path[path]["missing_required_html_texts"])
            self.assertIn("data-turn-root", by_path[path]["forbidden_html_texts"])
            self.assertEqual([], by_path[path]["forbidden_html_hits"])

        self.assertEqual(f"{self.base_url}/mobile/player", by_path["/play"]["final_url"])
        self.assertEqual("/mobile/player", by_path["/play"]["required_final_url_prefix"])
        self.assertEqual(
            [f"{self.base_url}/mobile/player"],
            by_path["/play"]["redirect_chain"],
        )
        self.assertIn("/play/continuity", by_path)
        self.assertIn(
            "NEXUS-PAN continuity",
            by_path["/play/continuity"]["required_texts"],
        )

    def test_flagship_contract_tracks_production_public_boundaries(self) -> None:
        module = load_module()
        landing_source = (
            REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Landing.cshtml"
        ).read_text(encoding="utf-8")
        status_source = (
            REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Status.cshtml"
        ).read_text(encoding="utf-8")
        participate_source = (
            REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Partizipate.cshtml"
        ).read_text(encoding="utf-8")
        mobile_source = (
            REPO_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "MobileProjection.cshtml"
        ).read_text(encoding="utf-8")
        controller_source = (
            REPO_ROOT / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"
        ).read_text(encoding="utf-8")

        landing = module.build_landing_surface(
            release_review_required=True,
            downloads_paused=False,
            downloads_under_review=True,
        )
        for marker in (
            'href="/build"',
            'href="/mobile/player"',
            'data-public-install-handoff="true"',
        ):
            self.assertIn(marker, landing_source)
            self.assertIn(marker, landing["required_html_texts"])
        self.assertIn('"Downloads under review"', status_source)

        participate = next(item for item in module.SURFACES if item["path"] == "/participate")
        self.assertIn("data-chummer-participate-frame", participate_source)
        self.assertIn('referrerpolicy="same-origin"', participate_source)
        self.assertIn('return $"{route}?embed=1";', controller_source)
        self.assertIn('src="/participate/board?embed=1"', participate["required_html_texts"])
        self.assertIn("productlift.dev", participate["forbidden_html_texts"])

        gm = next(item for item in module.SURFACES if item["path"] == "/mobile/gm")
        for marker in (
            'data-play-surface="install-only"',
            'data-live-session="unavailable"',
            'data-authority="none"',
            "data-install-role=",
            "data-role-capabilities=",
            "data-role-privacy-warning=",
            "data-role-authority-warning=",
        ):
            self.assertIn(marker, mobile_source)
        self.assertIn('data-install-role="gm"', gm["required_html_texts"])
        self.assertIn('return Redirect($"/mobile/{canonicalRole}");', controller_source)

    def test_verify_fails_when_mobile_gm_surface_loses_role_boundary(self) -> None:
        module = load_module()
        _SurfaceHandler.mobile_gm_missing_heading = True

        payload = module.verify(self.base_url)

        self.assertEqual("fail", payload["status"])
        gm = next(item for item in payload["results"] if item["path"] == "/mobile/gm")
        self.assertIn('data-install-role="gm"', gm["missing_required_html_texts"])
        self.assertIn('data-role-capabilities="gm"', gm["missing_required_html_texts"])
        self.assertIn(
            '/mobile/gm: missing required html text: data-install-role="gm", data-role-capabilities="gm", data-role-privacy-warning="gm", data-role-authority-warning="gm"',
            payload["failures"],
        )

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
