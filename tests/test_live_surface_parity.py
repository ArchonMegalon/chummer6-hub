from __future__ import annotations

import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_live_surface_parity.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_live_surface_parity", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _SurfaceHandler(BaseHTTPRequestHandler):
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
                b"Install Chummer Current public installer: Windows. Current build Newest build Nightly Stable "
                b"Use this when you want the newest promoted build. Help"
                b"</body></html>"
            )
            return

        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"Current release The build, platforms, and current state in one place. "
                b"Release Open downloads Open help Platforms"
                b"</body></html>"
            )
            return

        if self.path == "/participate":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"<section class=\"partizipate-board\">Participate Short requests, clear bugs, useful ideas.</section>"
                b"</body></html>"
            )
            return

        if self.path == "/partizipate":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"<section class=\"partizipate-board\">Participate Short requests, clear bugs, useful ideas.</section>"
                b"</body></html>"
            )
            return

        if self.path == "/participate/board":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"<title>Participate - Chummer.run</title>"
                b"<meta name=\"description\" content=\"Short requests, clear bugs, useful ideas.\">"
                b"<style data-chummer-board-skin></style>"
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

    def test_verify_requires_public_participate_surfaces(self) -> None:
        module = load_module()

        payload = module.verify(self.base_url)

        self.assertEqual("pass", payload["status"])

        participate = next(item for item in payload["results"] if item["path"] == "/participate")
        self.assertEqual(200, participate["status_code"])
        self.assertFalse(participate["cross_origin_redirect"])
        self.assertEqual([], participate["missing_required_texts"])
        self.assertEqual([], participate["missing_required_html_texts"])
        self.assertEqual([], participate["forbidden_html_hits"])

        board = next(item for item in payload["results"] if item["path"] == "/participate/board")
        self.assertEqual(200, board["status_code"])
        self.assertFalse(board["cross_origin_redirect"])
        self.assertEqual([], board["missing_required_texts"])
        self.assertEqual([], board["forbidden_hits"])

    def test_verify_blocks_participate_iframe_wrapper(self) -> None:
        module = load_module()
        participate_surface = next(item for item in module.SURFACES if item["path"] == "/participate")

        self.assertIn('class="partizipate-board', participate_surface["required_html_texts"])
        self.assertIn('id="participate-board"', participate_surface["forbidden_html_texts"])
        self.assertIn('src="/participate/board"', participate_surface["forbidden_html_texts"])

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
        self.assertIn("Participate - Chummer.run", board_surface["required_texts"])
        self.assertIn("<title>Participate - Chummer.run</title>", board_surface["required_html_texts"])
        self.assertIn("data-chummer-board-skin", board_surface["required_html_texts"])

    def test_mainline_payload_remains_json_serializable(self) -> None:
        module = load_module()

        payload = module.verify(self.base_url)

        serialized = json.dumps(payload)
        self.assertIn("LIVE_SURFACE_PARITY_READY", serialized)


if __name__ == "__main__":
    unittest.main()
