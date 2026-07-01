from __future__ import annotations

import importlib.util
import json
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
    return module


class _SurfaceHandler(BaseHTTPRequestHandler):
    billing_mode = "configured"

    def do_GET(self):  # noqa: N802
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"A Shadowrun character manager for clean sheets and faster tables."
                b"<a>Download Chummer</a><a>Current public installer: Windows.</a><a>Help</a><a>Status</a><a>Watch 90 sec</a>"
                b"</body></html>"
            )
            return

        if self.path == "/downloads":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"Downloads Chummer selects the best installer when it can. Stable release. Nightly Stable Build from source Download script"
                b"</body></html>"
            )
            return

        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"<section class=\"minimal-page-hero minimal-status-pill\">"
                b"<h1>Updated</h1>"
                b"<a href=\"/downloads\">Downloads</a>"
                b"<a href=\"/help\">Help</a>"
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
                        b"Supporter Email first. Billing stays attached after this step. After this step, Chummer returns to billing. Continue with email Continue with Google"
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
                b"<meta name=\"description\" content=\"Public requests, clear bugs, useful ideas.\">"
                b"<h1>Participate</h1>"
                b"<iframe src=\"https://chummer6.productlift.dev/\" data-chummer-participate-frame></iframe>"
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
        self.assertIn("productlift.dev", participate_surface["required_html_texts"])
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
        self.assertEqual([], billing["forbidden_hits"])

    def test_verify_rejects_placeholder_billing_surface_when_live_checkout_is_required(self) -> None:
        module = load_module()
        _SurfaceHandler.billing_mode = "placeholder"
        with mock.patch.dict("os.environ", {"CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT": "1"}, clear=False):
            payload = module.verify(self.base_url)

        self.assertEqual("fail", payload["status"])
        billing = next(item for item in payload["results"] if item["path"] == "/account/billing")
        self.assertIn("Email first. Billing stays attached after this step.", billing["missing_required_texts"])
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


if __name__ == "__main__":
    unittest.main()
