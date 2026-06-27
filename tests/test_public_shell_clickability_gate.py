from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_public_shell_clickability.py"


class _PublicShellFixtureHandler(BaseHTTPRequestHandler):
    BAD_COPY = False
    BAD_LINK = False
    BAD_DUPLICATE_LINK = False
    GOOD_HITS = 0

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/status", "/downloads", "/help", "/contact", "/login?next=%2F", "/account/billing", "/feedback", "/participate", "/roadmap", "/what-is-chummer"}:
            body = f"""
            <html><body>
              <a href="/status">status</a>
              <a href="/downloads">downloads</a>
              <a href="/help">help</a>
              <a href="/contact">contact</a>
              <a href="/login?next=%2F">login</a>
              <a href="/account/billing">billing</a>
              <a href="/feedback">feedback</a>
              <a href="/participate">participate</a>
              <a href="/roadmap">roadmap</a>
              <a href="/what-is-chummer">what-is-chummer</a>
              {"<a href='/participate/participate'>bad-duplicate</a>" if self.BAD_DUPLICATE_LINK else ""}
              <a href="/auth/google/start?next=%2Fdownloads">sign-in</a>
              <a href="/good">good</a>
              {"<a href='/missing'>missing</a>" if self.BAD_LINK else ""}
              {"Load Demo Runner" if self.BAD_COPY else ""}
            </body></html>
            """
            self._send_html(200, body)
            return
        if self.path == "/good":
            type(self).GOOD_HITS += 1
            self._send_html(200, "<html><body>ok</body></html>")
            return
        if self.path.startswith("/auth/google/start"):
            self.send_response(302)
            self.send_header("Location", "https://accounts.example.invalid/o/oauth2/v2/auth")
            self.end_headers()
            return

        self._send_html(404, "<html><body>missing</body></html>")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_html(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


class PublicShellClickabilityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        _PublicShellFixtureHandler.BAD_COPY = False
        _PublicShellFixtureHandler.BAD_LINK = False
        _PublicShellFixtureHandler.BAD_DUPLICATE_LINK = False
        _PublicShellFixtureHandler.GOOD_HITS = 0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _PublicShellFixtureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def run_script(self) -> tuple[subprocess.CompletedProcess[str], dict]:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "clickability.json"
            completed = subprocess.run(
                ["python3", str(SCRIPT), "--base-url", self.base_url, "--output", str(output_path)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        return completed, payload

    def test_gate_passes_when_public_pages_are_clickable_and_clean(self) -> None:
        completed, payload = self.run_script()

        self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["summary"]["failed_page_count"], 0)
        self.assertEqual(payload["summary"]["failed_link_count"], 0)

    def test_gate_fails_on_forbidden_public_copy(self) -> None:
        _PublicShellFixtureHandler.BAD_COPY = True
        completed, payload = self.run_script()

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["status"], "fail")
        self.assertIn("/status", payload["summary"]["failed_pages"])

    def test_gate_fails_on_broken_same_origin_link(self) -> None:
        _PublicShellFixtureHandler.BAD_LINK = True
        completed, payload = self.run_script()

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["status"], "fail")
        self.assertGreater(payload["summary"]["failed_link_count"], 0)

    def test_gate_fails_on_duplicated_first_party_shell_link(self) -> None:
        _PublicShellFixtureHandler.BAD_DUPLICATE_LINK = True
        completed, payload = self.run_script()

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["status"], "fail")
        self.assertIn("/participate/participate", payload["summary"]["suspicious_links"])
        self.assertIn("/", payload["summary"]["failed_pages"])

    def test_gate_reuses_cached_result_for_repeated_same_origin_links(self) -> None:
        completed, payload = self.run_script()

        self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(_PublicShellFixtureHandler.GOOD_HITS, 1)


if __name__ == "__main__":
    unittest.main()
