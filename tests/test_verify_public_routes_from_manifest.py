from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_public_routes_from_manifest.py"


class _RouteFixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send_text(200, "landing")
            return
        if self.path == "/public":
            self._send_text(200, "public")
            return
        if self.path == "/login" or self.path.startswith("/login?"):
            self._send_text(200, "login")
            return
        if self.path == "/private":
            self.send_response(302)
            self.send_header("Location", "/login?next=%2Fprivate")
            self.end_headers()
            return
        if self.path == "/logout":
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return
        if self.path == "/auth/email/start":
            self.send_response(405)
            self.send_header("Allow", "POST")
            self.end_headers()
            return
        if self.path == "/auth/email/callback":
            self._send_text(400, "ticket is required")
            return
        if self.path == "/auth/google/start":
            self.send_response(302)
            self.send_header("Location", "https://accounts.example.invalid/o/oauth2/v2/auth")
            self.end_headers()
            return

        self._send_text(404, "missing")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_text(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


class VerifyPublicRoutesFromManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RouteFixtureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def run_script(self, manifest_payload: dict) -> tuple[subprocess.CompletedProcess[str], dict]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            manifest_path = temp_root / "PUBLIC_LANDING_MANIFEST.yaml"
            report_path = temp_root / "route-proof.json"
            manifest_path.write_text(yaml.safe_dump(manifest_payload, sort_keys=False), encoding="utf-8")
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--base-url",
                    self.base_url,
                    "--manifest",
                    str(manifest_path),
                    "--output",
                    str(report_path),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
        return completed, report

    def test_verifier_succeeds_for_public_registered_and_auth_routes(self) -> None:
        manifest = {
            "surface": "chummer.run",
            "version": 1,
            "public_routes": [
                {
                    "path": "/public",
                    "audience": "public",
                    "purpose": "proof_shelf",
                    "requires_auth": False,
                    "guest_fallback": "/public",
                    "must_exist": True,
                },
                {
                    "path": "/private",
                    "audience": "registered",
                    "purpose": "signed_in_dashboard",
                    "requires_auth": True,
                    "guest_fallback": "/login?next=/private",
                    "must_exist": True,
                },
                {
                    "path": "/logout",
                    "audience": "registered",
                    "purpose": "session_exit",
                    "requires_auth": True,
                    "guest_fallback": "/",
                    "must_exist": True,
                },
                {
                    "path": "/auth/email/start",
                    "audience": "public",
                    "purpose": "auth_operation",
                    "requires_auth": False,
                    "guest_fallback": "/login",
                    "must_exist": True,
                },
                {
                    "path": "/auth/email/callback",
                    "audience": "public",
                    "purpose": "auth_operation",
                    "requires_auth": False,
                    "guest_fallback": "/login",
                    "must_exist": True,
                },
                {
                    "path": "/auth/google/start",
                    "audience": "public",
                    "purpose": "auth_operation",
                    "requires_auth": False,
                    "guest_fallback": "/login",
                    "must_exist": True,
                },
            ],
        }

        completed, report = self.run_script(manifest)

        self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
        self.assertEqual(report["summary"]["failed_count"], 0)
        self.assertEqual(report["summary"]["route_count"], 6)
        self.assertEqual(report["summary"]["registered_route_count"], 2)
        self.assertEqual(report["summary"]["auth_operation_count"], 3)

    def test_verifier_reports_registered_fallback_mismatch(self) -> None:
        manifest = {
            "surface": "chummer.run",
            "version": 1,
            "public_routes": [
                {
                    "path": "/private",
                    "audience": "registered",
                    "purpose": "signed_in_dashboard",
                    "requires_auth": True,
                    "guest_fallback": "/auth/google/start?next=/private",
                    "must_exist": True,
                }
            ],
        }

        completed, report = self.run_script(manifest)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["summary"]["failed_count"], 1)
        self.assertEqual(report["summary"]["failed_paths"], ["/private"])
        self.assertIn("expected anonymous redirect", report["routes"][0]["detail"])


if __name__ == "__main__":
    unittest.main()
