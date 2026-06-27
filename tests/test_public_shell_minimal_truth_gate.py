from __future__ import annotations

import importlib.util
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "public_shell_minimal_truth_gate.py"
SPEC = importlib.util.spec_from_file_location("public_shell_minimal_truth_gate", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(SCRIPT.parent))
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class _PublicShellMinimalTruthHandler(BaseHTTPRequestHandler):
    BAD_CONTACT_COPY = False
    EMPTY_LOGIN_META = False
    BAD_ALIAS = False

    def do_GET(self) -> None:  # noqa: N802
        path = self.path
        if path == "/partizipate" and not type(self).BAD_ALIAS:
            self.send_response(302)
            self.send_header("Location", "/participate")
            self.end_headers()
            return
        if path == "/participate":
            self._send_html(
                200,
                """
                <html>
                  <head>
                    <base href="/participate/" />
                    <title>Participate - Chummer.run</title>
                    <meta property="og:title" content="Public bugs and requests - Chummer.run" />
                  </head>
                  <body>
                    <style data-chummer-board-skin></style>
                  </body>
                </html>
                """,
            )
            return
        if path == "/partizipate":
            self._send_html(200, "<html><body>wrong alias target</body></html>")
            return
        if path == "/contact":
            body = """
            <html>
              <head>
                <meta property="og:url" content="/contact" />
                <meta name="twitter:url" content="/contact" />
              </head>
              <body>
                <a href="https://discord.gg/chummer">Open Discord</a>
                <p>Use this page for private details.</p>
              </body>
            </html>
            """
            if type(self).BAD_CONTACT_COPY:
                body = body.replace("</body>", "<p>Open Participate</p></body>")
            self._send_html(200, body)
            return
        if path == "/login?next=%2F":
            og_value = "" if type(self).EMPTY_LOGIN_META else "/login?next=%2F"
            self._send_html(
                200,
                f"""
                <html>
                  <head>
                    <meta property="og:url" content="{og_value}" />
                    <meta name="twitter:url" content="/login?next=%2F" />
                  </head>
                  <body>
                    <a href="/auth/email/start">Continue with email</a>
                  </body>
                </html>
                """,
            )
            return
        if path == "/account/billing":
            self._send_html(
                200,
                """
                <html>
                  <head>
                    <meta property="og:url" content="/account/billing" />
                    <meta name="twitter:url" content="/account/billing" />
                  </head>
                  <body>
                    <p>Supporter checkout is unavailable right now.</p>
                  </body>
                </html>
                """,
            )
            return
        if path == "/downloads":
            self._send_html(
                200,
                """
                <html>
                  <head>
                    <meta property="og:url" content="/downloads" />
                    <meta name="twitter:url" content="/downloads" />
                  </head>
                  <body>
                    <p>Stable</p>
                    <p>Nightly</p>
                    <p>Build</p>
                  </body>
                </html>
                """,
            )
            return
        if path == "/status":
            self._send_html(
                200,
                """
                <html>
                  <head>
                    <meta property="og:url" content="/status" />
                    <meta name="twitter:url" content="/status" />
                  </head>
                  <body>
                    <p>Updated</p>
                  </body>
                </html>
                """,
            )
            return

        self._send_html(404, "<html><body>missing</body></html>")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_html(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


class PublicShellMinimalTruthGateTests(unittest.TestCase):
    def setUp(self) -> None:
        _PublicShellMinimalTruthHandler.BAD_CONTACT_COPY = False
        _PublicShellMinimalTruthHandler.EMPTY_LOGIN_META = False
        _PublicShellMinimalTruthHandler.BAD_ALIAS = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _PublicShellMinimalTruthHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_gate_passes_when_routes_stay_minimal_and_first_party(self) -> None:
        payload = MODULE.evaluate(base_url=self.base_url, timeout=5.0)

        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["failure_count"], 0)

    def test_gate_fails_when_contact_page_leaks_participate_detour(self) -> None:
        _PublicShellMinimalTruthHandler.BAD_CONTACT_COPY = True

        payload = MODULE.evaluate(base_url=self.base_url, timeout=5.0)

        self.assertEqual(payload["status"], "fail")
        self.assertTrue(any("/contact:" in failure for failure in payload["failures"]))
        self.assertTrue(any("Open Participate" in failure for failure in payload["failures"]))

    def test_gate_fails_when_login_meta_url_is_empty(self) -> None:
        _PublicShellMinimalTruthHandler.EMPTY_LOGIN_META = True

        payload = MODULE.evaluate(base_url=self.base_url, timeout=5.0)

        self.assertEqual(payload["status"], "fail")
        self.assertTrue(any("/login?next=%2F:" in failure for failure in payload["failures"]))
        self.assertTrue(any("og:url is missing or empty" in failure for failure in payload["failures"]))

    def test_gate_fails_when_partizipate_alias_stops_resolving_to_participate(self) -> None:
        _PublicShellMinimalTruthHandler.BAD_ALIAS = True

        payload = MODULE.evaluate(base_url=self.base_url, timeout=5.0)

        self.assertEqual(payload["status"], "fail")
        self.assertTrue(any("/partizipate:" in failure for failure in payload["failures"]))
        self.assertTrue(any("instead of /participate" in failure for failure in payload["failures"]))

    def test_publish_lane_calls_public_shell_minimal_truth_gate(self) -> None:
        publish_script = (ROOT / "scripts" / "publish-download-bundle-http.sh").read_text(encoding="utf-8")
        verify_script = (ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        janitor_script = (ROOT / "scripts" / "run_gold_janitor.py").read_text(encoding="utf-8")

        self.assertIn("CHUMMER_RELEASE_UPLOAD_VERIFY_PUBLIC_SHELL_TRUTH", publish_script)
        self.assertIn('python3 "$SCRIPT_DIR/public_shell_minimal_truth_gate.py"', publish_script)
        self.assertIn("test_public_shell_minimal_truth_gate.py", verify_script)
        self.assertIn('python3 "$ROOT_DIR/scripts/public_shell_minimal_truth_gate.py"', verify_script)
        self.assertIn('["python3", "scripts/public_shell_minimal_truth_gate.py", "--base-url", base_url]', janitor_script)


if __name__ == "__main__":
    unittest.main()
