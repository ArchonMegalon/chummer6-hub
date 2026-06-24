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
                b"<a>Download Chummer</a><a>Windows and Linux.</a><a>Help</a><a>Status</a><a>Watch 90 sec</a>"
                b"</body></html>"
            )
            return

        if self.path == "/downloads":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body>"
                b"Install Chummer Windows and Linux installers. Current build Newest build Nightly Stable "
                b"Use this when you want the latest Windows or Linux build. Help"
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

        if self.path == "/partizipate":
            self.send_response(302)
            self.send_header("Location", "https://accounts.google.com/v3/signin/identifier")
            self.end_headers()
            return

        if self.path == "/partizipate/board":
            self.send_response(302)
            self.send_header("Location", "/auth/google/start?next=%2Fpartizipate")
            self.end_headers()
            return

        if self.path.startswith("/auth/google/start"):
            self.send_response(302)
            self.send_header("Location", "https://accounts.google.com/v3/signin/identifier")
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

    def test_verify_marks_redirected_participate_surfaces_as_failures(self) -> None:
        module = load_module()

        payload = module.verify(self.base_url)

        self.assertEqual("fail", payload["status"])
        failure_text = "\n".join(payload["failures"])
        self.assertIn("/partizipate: expected 200, got 302", failure_text)
        self.assertIn("/partizipate: redirected off-origin to https://accounts.google.com/v3/signin/identifier", failure_text)
        self.assertIn("/partizipate/board: expected 200, got 302", failure_text)
        self.assertIn("/partizipate/board: redirected off-origin to https://accounts.google.com/v3/signin/identifier", failure_text)

        participate = next(item for item in payload["results"] if item["path"] == "/partizipate")
        self.assertEqual(302, participate["status_code"])
        self.assertTrue(participate["cross_origin_redirect"])
        self.assertEqual(
            "https://accounts.google.com/v3/signin/identifier",
            participate["redirect_target_url"],
        )

        board = next(item for item in payload["results"] if item["path"] == "/partizipate/board")
        self.assertEqual(302, board["status_code"])
        self.assertEqual(
            [
                f"{self.base_url}/auth/google/start?next=%2Fpartizipate",
                "https://accounts.google.com/v3/signin/identifier",
            ],
            board["redirect_chain"],
        )

    def test_mainline_payload_remains_json_serializable(self) -> None:
        module = load_module()

        payload = module.verify(self.base_url)

        serialized = json.dumps(payload)
        self.assertIn("LIVE_SURFACE_PARITY_NOT_READY", serialized)


if __name__ == "__main__":
    unittest.main()
