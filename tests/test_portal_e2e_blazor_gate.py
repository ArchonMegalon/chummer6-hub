from __future__ import annotations

import os
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "e2e-portal.cjs"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "ai" / "verify.sh"


class _PortalFixtureHandler(BaseHTTPRequestHandler):
    blazor_mode = "fallback"
    blazor_interaction_mode = "interactive"
    blazor_transient_failures_remaining = 0
    billing_mode = "configured"
    auth_mode = "email_and_google"

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path == "/":
            self._send_html(
                """
                <html><body>
                <h1>Chummer</h1>
                <p>Current public installer: Windows.</p>
                <p>Current public lane: Preview. Review required.</p>
                <div class="minimal-open-chummer">
                <button class="site-open-chummer-menu__button site-open-chummer-menu__button--disabled" disabled data-disabled-target="/build" data-sign-in-href="/login?next=%2Fbuild">Build</button>
                <button class="site-open-chummer-menu__button site-open-chummer-menu__button--disabled" disabled data-disabled-target="/mobile/player" data-sign-in-href="/login?next=%2Fmobile%2Fplayer">Play</button>
                <a href="/login?next=%2Faccount%2Faccess">Sign in first</a>
                <span>Open Chummer</span>
                </div>
                <a href="/media/promo/every-wonder-horizon-promo.mp4">Product reel</a>
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
                <p>Current public installer</p>
                <p>Stable</p>
                <p>Nightly</p>
                <p>Preview build. Review required.</p>
                <p>Version run-20260627-005402</p>
                <p>Build from source</p>
                <a href="/downloads/source">Download script</a>
                <a href="/help">Help</a>
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
                <h1>Now</h1>
                <p>Preview downloads</p>
                <p>Updated 2026-07-01T05:00:00Z</p>
                <p>Downloads</p>
                <p>Version run-20260627-005402</p>
                <a href="/help">Help</a>
                </body></html>
                """
            )
            return

        if path == "/login":
            billing_login = "next=%2Faccount%2Fbilling" in self.path or "next=/account/billing" in self.path
            auth_mode = self.auth_mode
            if billing_login and self.billing_mode == "google_only":
                auth_mode = "google_only"
            if auth_mode == "google_only":
                hint = "Google first. Billing stays attached after that step." if billing_login else "Email sign-in is unavailable on this host right now. Continue with Google instead."
                body = """
                <html><body>
                <h1>{heading}</h1>
                <p>{hint}</p>
                <p>{meta}</p>
                <a href="/auth/google/start">Continue with Google</a>
                </body></html>
                """
            else:
                hint = "Email first. Billing stays attached after this step." if billing_login else "Email first. Google if you prefer."
                body = """
                <html><body>
                <h1>{heading}</h1>
                <p>{hint}</p>
                <p>{meta}</p>
                <button>Continue with email</button>
                <a href="/auth/google/start">Continue with Google</a>
                </body></html>
                """
            self._send_html(
                body.format(
                    heading="Supporter" if billing_login else "Open Chummer",
                    hint=hint,
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
            if self.billing_mode in {"configured", "google_only"}:
                self._send_html(
                    """
                    <html><body>
                    <h1>Supporter</h1>
                    <p>{hint}</p>
                    <p>After this step, Chummer returns to billing.</p>
                    {actions}
                    </body></html>
                    """.format(
                        hint="Google first. Billing stays attached after that step." if self.billing_mode == "google_only" else "Email first. Billing stays attached after this step.",
                        actions='<button>Continue with email</button><button>Continue with Google</button>' if self.billing_mode == "configured" else '<button>Continue with Google</button>',
                    )
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
                <h1>Participate</h1>
                <h2>Current requests</h2>
                <iframe src="/participate/board?embed=1" data-chummer-participate-frame></iframe>
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
                <p>Planned work and current requests.</p>
                <div>data-chummer-roadmap-frame</div>
                </body></html>
                """
            )
            return

        if path == "/roadmap/board":
            self.send_response(302)
            self.send_header("Location", "/participate")
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
            if self.blazor_transient_failures_remaining > 0:
                type(self).blazor_transient_failures_remaining -= 1
                self.send_response(524)
                self.end_headers()
                return
            if self.blazor_mode == "ready":
                self._send_html(
                    """
                    <html>
                    <head><base href="/blazor/"></head>
                    <body>
                    <span>Chummer Online</span>
                    <h1>Character Roster</h1>
                    <a href="/blazor/app?command=new_character">New runner</a>
                    <a href="/blazor/app?command=open_character">Import</a>
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

        if path == "/blazor/app":
            if self.blazor_mode == "ready":
                leave_occluding_backdrop = self.blazor_interaction_mode != "interactive"
                self._send_html(
                    f"""
                    <html>
                    <head>
                    <style>
                    body {{ font-family: sans-serif; margin: 0; }}
                    .menu-shell {{ position: fixed; top: 0; left: 0; z-index: 20; padding: 12px; }}
                    .menu-btn {{ background: #fff; border: 1px solid #111; padding: 8px 12px; }}
                    .menu-dropdown {{ position: absolute; top: 48px; left: 12px; display: none; background: #fff; border: 1px solid #111; z-index: 21; }}
                    .desktop-shell--dialog-open .menu-shell {{ z-index: 1001; }}
                    .desktop-shell--dialog-open .menu-dropdown {{ z-index: 1002; }}
                    .dialog-backdrop {{ position: fixed; inset: 0; z-index: 999; background: rgba(0, 0, 0, 0.08); }}
                    .desktop-dialog {{ position: fixed; top: 72px; left: 32px; z-index: 1000; background: #fff; border: 1px solid #111; padding: 20px; width: 360px; }}
                    .desktop-dialog label {{ display: block; margin-top: 12px; }}
                    .desktop-dialog span {{ display: block; margin-bottom: 4px; }}
                    </style>
                    </head>
                    <body class="desktop-shell--dialog-open">
                    <div class="menu-shell">
                      <button type="button" role="menuitem" class="menu-btn classic-menu-button" aria-expanded="false" disabled>File</button>
                      <button type="button" class="tool-btn classic-tool-button" disabled>New</button>
                      <div class="menu-dropdown">
                        <button type="button" class="menu-item classic-menu-item">New runner</button>
                      </div>
                    </div>
                    <div id="dialogBackdrop" class="dialog-backdrop" data-dialog-id="dialog.new_character"></div>
                    <div class="desktop-dialog">
                      <h1 id="dialogTitle">Select Build Method</h1>
                      <label data-field-id="newCharacterName">
                        <span>Character Name</span>
                        <input aria-label="Character Name" value="" />
                      </label>
                      <label data-field-id="newCharacterRuleset">
                        <span>Ruleset</span>
                        <select aria-label="Ruleset"><option value="sr6" selected>SR6</option></select>
                      </label>
                      <label data-field-id="newCharacterBuildMethod">
                        <span>Build Method</span>
                        <select aria-label="Build Method">
                          <option value="Priority" selected>Priority</option>
                          <option value="Karma">Karma</option>
                        </select>
                      </label>
                      <button type="button" id="dialogClose">Close</button>
                    </div>
                    <script>
                    const fileButton = document.querySelector('button.menu-btn.classic-menu-button');
                    const newToolButton = document.querySelector('button.tool-btn.classic-tool-button');
                    const dropdown = document.querySelector('.menu-dropdown');
                    const buildMethod = document.querySelector('label[data-field-id="newCharacterBuildMethod"] select');
                    const newRunner = document.querySelector('button.menu-item.classic-menu-item');
                    const dialog = document.querySelector('.desktop-dialog');
                    const dialogClose = document.querySelector('#dialogClose');
                    const backdrop = document.querySelector('#dialogBackdrop');
                    const leaveOccludingBackdrop = {str(leave_occluding_backdrop).lower()};
                    fileButton.addEventListener('click', () => {{
                      const expanded = fileButton.getAttribute('aria-expanded') === 'true';
                      fileButton.setAttribute('aria-expanded', expanded ? 'false' : 'true');
                      dropdown.style.display = expanded ? 'none' : 'block';
                    }});
                    dialogClose.addEventListener('click', () => {{
                      if (leaveOccludingBackdrop) {{
                        backdrop.removeAttribute('data-dialog-id');
                      }} else {{
                        backdrop.remove();
                      }}
                      dialog.style.display = 'none';
                      document.body.classList.remove('desktop-shell--dialog-open');
                      fileButton.disabled = false;
                      newToolButton.disabled = false;
                    }});
                    newRunner.addEventListener('click', () => {{
                      buildMethod.value = 'Priority';
                      backdrop.setAttribute('data-dialog-id', 'dialog.new_character');
                      if (!backdrop.isConnected) {{
                        document.body.appendChild(backdrop);
                      }}
                      dialog.style.display = 'block';
                      document.body.classList.add('desktop-shell--dialog-open');
                      fileButton.disabled = true;
                      newToolButton.disabled = true;
                      fileButton.setAttribute('aria-expanded', 'false');
                      dropdown.style.display = 'none';
                    }});
                    </script>
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
    def test_authoritative_verify_requires_blazor_by_default(self) -> None:
        verify_script = VERIFY_SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            'CHUMMER_PORTAL_REQUIRE_BLAZOR="${CHUMMER_HUB_PUBLIC_REQUIRE_BLAZOR:-1}"',
            verify_script,
        )

    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _PortalFixtureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def run_script(
        self,
        *,
        require_blazor: bool,
        blazor_mode: str,
        blazor_interaction_mode: str = "interactive",
        blazor_transient_failures: int = 0,
        require_billing_checkout: bool = False,
        billing_mode: str = "configured",
        auth_mode: str = "email_and_google",
    ) -> subprocess.CompletedProcess[str]:
        _PortalFixtureHandler.blazor_mode = blazor_mode
        _PortalFixtureHandler.blazor_interaction_mode = blazor_interaction_mode
        _PortalFixtureHandler.blazor_transient_failures_remaining = blazor_transient_failures
        _PortalFixtureHandler.billing_mode = billing_mode
        _PortalFixtureHandler.auth_mode = auth_mode
        env = os.environ.copy()
        env["CHUMMER_PORTAL_BASE_URL"] = self.base_url
        env["CHUMMER_PORTAL_RETRY_DELAY_MS"] = "1"
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
        self.assertIn(f"ok: {self.base_url}/blazor/app?command=new_character", combined)
        self.assertIn("portal E2E completed", combined)

    def test_blazor_ready_surface_recovers_from_one_transient_524(self) -> None:
        completed = self.run_script(
            require_blazor=True,
            blazor_mode="ready",
            blazor_transient_failures=1,
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
        combined = f"{completed.stdout}\n{completed.stderr}"
        self.assertIn("transient-retry:", combined)
        self.assertIn("HTTP 524", combined)
        self.assertIn("portal E2E completed", combined)

    def test_blazor_ready_surface_rejects_persistent_524(self) -> None:
        completed = self.run_script(
            require_blazor=True,
            blazor_mode="ready",
            blazor_transient_failures=3,
        )

        self.assertNotEqual(completed.returncode, 0)
        combined = f"{completed.stdout}\n{completed.stderr}"
        self.assertIn("Portal check failed", combined)
        self.assertIn("HTTP 524", combined)

    def test_blazor_ready_surface_blocks_gate_when_new_runner_menu_is_occluded(self) -> None:
        completed = self.run_script(
            require_blazor=True,
            blazor_mode="ready",
            blazor_interaction_mode="blocked",
        )

        self.assertNotEqual(completed.returncode, 0)
        combined = f"{completed.stdout}\n{completed.stderr}"
        self.assertIn("Portal check failed", combined)
        self.assertIn("/blazor/app?command=new_character", combined)
        self.assertIn("intercepts pointer events", combined)

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

    def test_google_only_auth_surfaces_pass_when_live_checkout_is_required(self) -> None:
        completed = self.run_script(
            require_blazor=False,
            blazor_mode="fallback",
            require_billing_checkout=True,
            billing_mode="google_only",
            auth_mode="google_only",
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
        combined = f"{completed.stdout}\n{completed.stderr}"
        self.assertIn(f"ok: {self.base_url}/account", combined)
        self.assertIn(f"ok: {self.base_url}/hub", combined)
        self.assertIn(f"ok: {self.base_url}/account/billing", combined)
        self.assertIn("portal E2E completed", combined)


if __name__ == "__main__":
    unittest.main()
