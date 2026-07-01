from __future__ import annotations

import importlib.util
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


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
    PRODUCTLIFT_LEAK = False
    UPSTREAM_ERROR = False
    PARTICIPATE_UNAVAILABLE = False
    CONFIGURED_BILLING_HANDOFF = False

    def do_GET(self) -> None:  # noqa: N802
        path = self.path
        if path == "/partizipate" and not type(self).BAD_ALIAS:
            self.send_response(302)
            self.send_header("Location", "/participate")
            self.end_headers()
            return
        if path == "/participate":
            if type(self).PARTICIPATE_UNAVAILABLE:
                self._send_html(
                    200,
                    """
                    <html>
                      <head>
                        <title>Participate - Chummer.run</title>
                        <link rel="canonical" href="/participate" />
                        <meta property="og:url" content="/participate" />
                        <meta name="twitter:url" content="/participate" />
                      </head>
                      <body>
                        <h1>Participate</h1>
                        <p>Board offline right now.</p>
                        <p>Use Contact for the Chummer5 Discord server.</p>
                        <a href="/contact">Contact</a>
                      </body>
                    </html>
                    """,
                )
                return
            self._send_html(
                200,
                """
                <html>
                  <head>
                    <link rel="canonical" href="/participate" />
                    <title>Participate - Chummer.run</title>
                    <meta property="og:title" content="Participate - Chummer.run" />
                    <meta property="og:url" content="/participate" />
                    <meta name="twitter:url" content="/participate" />
                  </head>
                  <body>
                    <h1>Participate</h1>
                    <iframe src="https://chummer6.productlift.dev/" title="Chummer participation board" data-chummer-participate-frame></iframe>
                  </body>
                </html>
                """,
            )
            return
        if path == "/partizipate":
            self._send_html(200, "<html><body>wrong alias target</body></html>")
            return
        if path == "/contact":
            twitter_url = "/contact"
            if type(self).PRODUCTLIFT_LEAK:
                twitter_url = "https://chummer6.productlift.dev/posts"
            body = """
            <html>
              <head>
                <meta property="og:url" content="/contact" />
                <meta name="twitter:url" content="{twitter_url}" />
              </head>
              <body>
                <a href="https://discord.gg/chummer">Open Discord</a>
                <p>Use this page for private details.</p>
              </body>
            </html>
            """
            body = body.format(twitter_url=twitter_url)
            if type(self).BAD_CONTACT_COPY:
                body = body.replace("</body>", "<p>Open Participate</p></body>")
            if type(self).UPSTREAM_ERROR:
                body = body.replace("</body>", "<p>Something went wrong on our side. Could not load posts.</p></body>")
            self._send_html(200, body)
            return
        if path.startswith("/login"):
            og_value = "" if type(self).EMPTY_LOGIN_META else path
            billing_login = "next=%2Faccount%2Fbilling" in self.path or "next=/account/billing" in self.path
            self._send_html(
                200,
                f"""
                <html>
                  <head>
                    <meta property="og:url" content="{og_value}" />
                    <meta name="twitter:url" content="/login?next=%2F" />
                  </head>
                  <body>
                    <h1>{"Supporter" if billing_login else "Open Chummer"}</h1>
                    <p>{"Email first. Billing stays attached after this step." if billing_login else "Email first. Google if you prefer."}</p>
                    <p>{"After this step, Chummer returns to billing." if billing_login else "After this step, Chummer returns to the signed-in product."}</p>
                    <a href="/auth/email/start">Continue with email</a>
                    <a href="/auth/google/start">Continue with Google</a>
                  </body>
                </html>
                """,
            )
            return
        if path == "/account/billing":
            if type(self).CONFIGURED_BILLING_HANDOFF:
                self.send_response(302)
                self.send_header("Location", "/login?next=%2Faccount%2Fbilling")
                self.end_headers()
                return
            self._send_html(
                200,
                """
                <html>
                  <head>
                    <meta property="og:url" content="/account/billing" />
                    <meta name="twitter:url" content="/account/billing" />
                  </head>
                  <body>
                    <h1>Membership</h1>
                    <p>Supporter is not open right now.</p>
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
                    <p>Downloads</p>
                    <p>Stable release</p>
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
                    <section class="minimal-page-hero minimal-status-pill">
                      <h1>Updated</h1>
                      <a href="/downloads">Downloads</a>
                      <a href="/help">Help</a>
                    </section>
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
        _PublicShellMinimalTruthHandler.PRODUCTLIFT_LEAK = False
        _PublicShellMinimalTruthHandler.UPSTREAM_ERROR = False
        _PublicShellMinimalTruthHandler.PARTICIPATE_UNAVAILABLE = False
        _PublicShellMinimalTruthHandler.CONFIGURED_BILLING_HANDOFF = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _PublicShellMinimalTruthHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_gate_passes_when_routes_stay_minimal_and_first_party(self) -> None:
        _PublicShellMinimalTruthHandler.CONFIGURED_BILLING_HANDOFF = True

        payload = MODULE.evaluate(base_url=self.base_url, timeout=5.0)

        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["failure_count"], 0)

    def test_gate_passes_when_live_billing_requires_first_party_sign_in_handoff(self) -> None:
        _PublicShellMinimalTruthHandler.CONFIGURED_BILLING_HANDOFF = True

        with mock.patch.dict(os.environ, {"CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT": "1"}, clear=False):
            payload = MODULE.evaluate(base_url=self.base_url, timeout=5.0)

        self.assertEqual(payload["status"], "pass")
        self.assertTrue(payload["require_brilliant_directories_checkout"])
        billing = next(item for item in payload["routes"] if item["route"] == "/account/billing")
        self.assertEqual("/login", billing["finalPath"])

    def test_gate_fails_when_live_billing_stays_on_placeholder_surface(self) -> None:
        with mock.patch.dict(os.environ, {"CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT": "1"}, clear=False):
            payload = MODULE.evaluate(base_url=self.base_url, timeout=5.0)

        self.assertEqual(payload["status"], "fail")
        self.assertTrue(any("/account/billing:" in failure for failure in payload["failures"]))
        self.assertTrue(any("Membership" in failure or "Supporter is not open right now." in failure for failure in payload["failures"]))

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

    def test_gate_fails_when_public_route_leaks_third_party_productlift_host(self) -> None:
        _PublicShellMinimalTruthHandler.PRODUCTLIFT_LEAK = True

        payload = MODULE.evaluate(base_url=self.base_url, timeout=5.0)

        self.assertEqual(payload["status"], "fail")
        self.assertTrue(any("twitter:url escaped the public host" in failure for failure in payload["failures"]))

    def test_gate_fails_when_upstream_error_copy_reappears(self) -> None:
        _PublicShellMinimalTruthHandler.UPSTREAM_ERROR = True

        payload = MODULE.evaluate(base_url=self.base_url, timeout=5.0)

        self.assertEqual(payload["status"], "fail")
        self.assertTrue(any("Something went wrong on our side. Could not load posts." in failure for failure in payload["failures"]))

    def test_gate_can_allow_local_participate_unavailable_fallback_explicitly(self) -> None:
        _PublicShellMinimalTruthHandler.PARTICIPATE_UNAVAILABLE = True
        _PublicShellMinimalTruthHandler.CONFIGURED_BILLING_HANDOFF = True

        failed_payload = MODULE.evaluate(base_url=self.base_url, timeout=5.0)
        passing_payload = MODULE.evaluate(base_url=self.base_url, timeout=5.0, allow_participate_unavailable=True)

        self.assertEqual(failed_payload["status"], "pass")
        self.assertEqual(passing_payload["status"], "pass")

    def test_publish_lane_calls_public_shell_minimal_truth_gate(self) -> None:
        publish_script = (ROOT / "scripts" / "publish-download-bundle-http.sh").read_text(encoding="utf-8")
        verify_script = (ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        janitor_script = (ROOT / "scripts" / "run_gold_janitor.py").read_text(encoding="utf-8")

        self.assertIn("CHUMMER_RELEASE_UPLOAD_VERIFY_PUBLIC_SHELL_TRUTH", publish_script)
        self.assertIn('python3 "$SCRIPT_DIR/public_shell_minimal_truth_gate.py"', publish_script)
        self.assertIn("test_public_shell_minimal_truth_gate.py", verify_script)
        self.assertIn('python3 "$ROOT_DIR/scripts/public_shell_minimal_truth_gate.py"', verify_script)
        self.assertIn('public_shell_command = ["python3", "scripts/public_shell_minimal_truth_gate.py", "--base-url", base_url]', janitor_script)
        self.assertIn('public_shell_command.append("--allow-participate-unavailable")', janitor_script)


if __name__ == "__main__":
    unittest.main()
