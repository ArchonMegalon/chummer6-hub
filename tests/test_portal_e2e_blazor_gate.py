from __future__ import annotations

import os
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "e2e-portal.cjs"


class _PortalFixtureHandler(BaseHTTPRequestHandler):
    blazor_mode = "fallback"
    billing_mode = "configured"

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path == "/":
            self._send_html(
                """
                <html><body>
                <h1>Chummer</h1>
                <a href="/downloads">Download Chummer</a>
                <p>Current public installer</p>
                <a href="/promo">Watch 90 sec</a>
                <a href="/downloads">/downloads</a>
                <a href="/help">/help</a>
                <a href="/status">/status</a>
                <a href="/contact">/contact</a>
                </body></html>
                """
            )
            return

        if path in {"/downloads", "/downloads/"}:
            self._send_html(
                """
                <html><body>
                <h1>Downloads</h1>
                <p>Main build for this browser</p>
                <p>Stable</p>
                <p>Nightly</p>
                <p>Build from source</p>
                <a href="/downloads/source">Download script</a>
                </body></html>
                """
            )
            return

        if path == "/downloads/releases.json":
            self._send_json('{"version":"0.0.0.1","channel":"stable","downloads":[{"platform":"windows"}]}')
            return

        if path == "/help":
            self._send_html(
                """
                <html><body>
                <h1>What is wrong?</h1>
                <p>Pick the next step.</p>
                <p>Install or update</p>
                <p>Account recovery</p>
                <p>Contact</p>
                <a href="/contact">Open contact</a>
                <a href="/faq">Read the FAQ</a>
                </body></html>
                """
            )
            return

        if path in {"/status", "/status/"}:
            self._send_html(
                """
                <html><body>
                <p>Status</p>
                <h1>Updated</h1>
                <p>Windows and Linux downloads are live.</p>
                <a href="/downloads">Downloads</a>
                <a href="/help">Help</a>
                </body></html>
                """
            )
            return

        if path == "/login":
            billing_login = "next=%2Faccount%2Fbilling" in self.path or "next=/account/billing" in self.path
            self._send_html(
                """
                <html><body>
                <h1>{heading}</h1>
                <p>{hint}</p>
                <p>{meta}</p>
                <button>Continue with email</button>
                <a href="/auth/google/start">Continue with Google</a>
                </body></html>
                """.format(
                    heading="Supporter" if billing_login else "Open Chummer",
                    hint="Email first. Billing stays attached after this step." if billing_login else "Email first. Google if you prefer.",
                    meta="After this step, Chummer returns to billing." if billing_login else "After this step, Chummer returns to the signed-in product.",
                )
            )
            return

        if path in {"/account", "/hub", "/hub/"}:
            target = "/login?next=%2Faccount"
            self.send_response(302)
            self.send_header("Location", target)
            self.end_headers()
            return

        if path == "/contact":
            self._send_html(
                """
                <html><body>
                <h1>Contact</h1>
                <p>Use the Chummer5 Discord server.</p>
                <p>Normal questions and feedback belong in the Chummer5 server.</p>
                <a href="https://discord.gg/chummer">Open Discord</a>
                <p>Chummer5 Discord</p>
                </body></html>
                """
            )
            return

        if path == "/account/billing":
            if self.billing_mode == "configured":
                self._send_html(
                    """
                    <html><body>
                    <h1>Supporter</h1>
                    <p>Email first. Billing stays attached after this step.</p>
                    <p>After this step, Chummer returns to billing.</p>
                    <button>Continue with email</button>
                    <button>Continue with Google</button>
                    </body></html>
                    """
                )
            else:
                self._send_html(
                    """
                    <html><body>
                    <h1>Membership</h1>
                    <p>Supporter is not open right now.</p>
                    <button>Continue with email</button>
                </body></html>
                """
                )
            return

        if path in {"/participate", "/participate/"}:
            self._send_html(
                """
                <html><body>
                <h1>What should Chummer do next?</h1>
                <p>Public requests, clear bugs, useful ideas.</p>
                <h2>Current requests</h2>
                <p>Board is live.</p>
                <iframe src="/participate/frame" data-chummer-participate-frame></iframe>
                <a href="/participate/p/better-roster-ux-ab12">Better roster UX</a>
                </body></html>
                """
            )
            return

        if path == "/participate/frame":
            self.send_response(302)
            self.send_header("Location", "/participate/board?embed=1")
            self.end_headers()
            return

        if path == "/participate/board":
            if "embed=1" in self.path:
                self._send_html(
                    """
                    <html>
                    <head><base href="/participate/board/" /></head>
                    <body><p>Chummer.run</p><p>embedded first-party board</p></body>
                    </html>
                    """
                )
            else:
                self.send_response(302)
                self.send_header("Location", "/participate")
                self.end_headers()
            return

        if path == "/roadmap":
            self._send_html(
                """
                <html><body>
                <h1>Roadmap</h1>
                <p>In progress.</p>
                <p>Planned work lives here. Shipped work moves to Changelog.</p>
                <p>Work opens below.</p>
                <div>data-chummer-roadmap-frame</div>
                </body></html>
                """
            )
            return

        if path == "/roadmap/board":
            self.send_response(302)
            self.send_header("Location", "/roadmap")
            self.end_headers()
            return

        if path == "/partizipate":
            self.send_response(302)
            self.send_header("Location", "/participate")
            self.end_headers()
            return

        if path == "/what-is-chummer":
            self._send_html("<html><body><h1>What Is Chummer?</h1></body></html>")
            return

        if path == "/artifacts":
            self._send_html(
                """
                <html><body>
                <h1>Detail gallery</h1>
                <p>Use this page for dossiers, recaps, and release details.</p>
                </body></html>
                """
            )
            return

        if path == "/faq":
            self._send_html("<html><body><h1>FAQ</h1></body></html>")
            return

        if path == "/blazor/":
            if self.blazor_mode == "ready":
                self._send_html(
                    """
                    <html>
                    <head><base href="/blazor/"></head>
                    <body>
                    <h1>Published browser client</h1>
                    <a href="/blazor/app">Launch browser workbench</a>
                    </body>
                    </html>
                    """
                )
            else:
                self._send_html(
                    """
                    <html><body>
                    <h1>Browser preview is not ready right now.</h1>
                    <a href="/downloads">Download Chummer</a>
                    <a href="/status">Status</a>
                    </body></html>
                    """
                )
            return

        if path == "/avalonia/":
            self.send_response(302)
            self.send_header("Location", "/downloads/")
            self.end_headers()
            return

        if path == "/session/":
            self.send_response(302)
            self.send_header("Location", "/play/")
            self.end_headers()
            return

        if path == "/play/":
            self._send_html("<html><body><h1>Player entry</h1></body></html>")
            return

        if path == "/coach/":
            self.send_response(302)
            self.send_header("Location", "/status/")
            self.end_headers()
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_html(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class PortalE2EBlazorGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _PortalFixtureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def run_script(self, *, require_blazor: bool, blazor_mode: str, require_billing_checkout: bool = False, billing_mode: str = "configured") -> subprocess.CompletedProcess[str]:
        _PortalFixtureHandler.blazor_mode = blazor_mode
        _PortalFixtureHandler.billing_mode = billing_mode
        env = os.environ.copy()
        env["CHUMMER_PORTAL_BASE_URL"] = self.base_url
        if require_blazor:
            env["CHUMMER_PORTAL_REQUIRE_BLAZOR"] = "1"
        else:
            env.pop("CHUMMER_PORTAL_REQUIRE_BLAZOR", None)
        if require_billing_checkout:
            env["CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT"] = "1"
        else:
            env.pop("CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT", None)

        return subprocess.run(
            ["node", str(SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_blazor_fallback_stays_non_blocking_when_not_required(self) -> None:
        completed = self.run_script(require_blazor=False, blazor_mode="fallback")

        self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
        combined = f"{completed.stdout}\n{completed.stderr}"
        self.assertIn(f"ok: {self.base_url}/blazor/", combined)
        self.assertIn("portal E2E completed", combined)

    def test_blazor_fallback_blocks_gate_when_required(self) -> None:
        completed = self.run_script(require_blazor=True, blazor_mode="fallback")

        self.assertNotEqual(completed.returncode, 0)
        combined = f"{completed.stdout}\n{completed.stderr}"
        self.assertIn("Portal check failed", combined)
        self.assertIn("/blazor/", combined)

    def test_blazor_ready_surface_passes_when_required(self) -> None:
        completed = self.run_script(require_blazor=True, blazor_mode="ready")

        self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
        combined = f"{completed.stdout}\n{completed.stderr}"
        self.assertIn(f"ok: {self.base_url}/blazor/", combined)
        self.assertIn("portal E2E completed", combined)

    def test_billing_placeholder_blocks_gate_when_live_checkout_is_required(self) -> None:
        completed = self.run_script(
            require_blazor=False,
            blazor_mode="fallback",
            require_billing_checkout=True,
            billing_mode="unavailable",
        )

        self.assertNotEqual(completed.returncode, 0)
        combined = f"{completed.stdout}\n{completed.stderr}"
        self.assertIn("Portal check failed", combined)
        self.assertIn("/account/billing", combined)

    def test_configured_billing_surface_passes_when_live_checkout_is_required(self) -> None:
        completed = self.run_script(
            require_blazor=False,
            blazor_mode="fallback",
            require_billing_checkout=True,
            billing_mode="configured",
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
        combined = f"{completed.stdout}\n{completed.stderr}"
        self.assertIn(f"ok: {self.base_url}/account/billing", combined)
        self.assertIn("portal E2E completed", combined)


if __name__ == "__main__":
    unittest.main()
