from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_public_routes_from_manifest.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_public_routes_from_manifest", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _RouteFixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send_text(200, "landing")
            return
        if self.path == "/public":
            self._send_text(200, "public")
            return
        if self.path == "/player":
            self.send_response(302)
            self.send_header("Location", "/mobile/player#")
            self.end_headers()
            return
        if self.path == "/mobile/player":
            self._send_text(200, "player")
            return
        if self.path == "/contact/submitted/sample-case-id":
            self._send_text(200, "sample support receipt")
            return
        if self.path == "/participate/karma-forge/submitted/sample-submission-id":
            self._send_text(200, "sample karma receipt")
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

    def run_script(self, manifest_payload: dict, extra_args: list[str] | None = None) -> tuple[subprocess.CompletedProcess[str], dict]:
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
                    *(extra_args or []),
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
                    "required_texts": ["public"],
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
        self.assertEqual(report["status"], "pass")
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
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["failed_count"], 1)
        self.assertEqual(report["summary"]["failed_paths"], ["/private"])
        self.assertIn("expected anonymous redirect", report["routes"][0]["detail"])

    def test_verifier_supports_controller_contract_routes_for_parameterized_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            controller_path = temp_root / "PublicLandingController.cs"
            controller_path.write_text(
                '[HttpGet("/contact/submitted/{caseId}")]\n'
                '[HttpGet("/participate/karma-forge/submitted/{submissionId}")]\n',
                encoding="utf-8",
            )
            manifest = {
                "surface": "chummer.run",
                "version": 1,
                "public_routes": [
                    {
                        "path": "/contact/submitted/{caseId}",
                        "audience": "public",
                        "purpose": "support_submission_receipt",
                        "requires_auth": False,
                        "guest_fallback": "/contact/submitted/{caseId}",
                        "must_exist": True,
                        "verification_mode": "controller_contract",
                        "verification_file": str(controller_path),
                        "verification_pattern": '[HttpGet("/contact/submitted/{caseId}")]',
                    },
                    {
                        "path": "/participate/karma-forge/submitted/{submissionId}",
                        "audience": "public",
                        "purpose": "governed_future_signal_receipt",
                        "requires_auth": False,
                        "guest_fallback": "/participate/karma-forge/submitted/{submissionId}",
                        "must_exist": True,
                        "verification_mode": "controller_contract",
                        "verification_file": str(controller_path),
                        "verification_pattern": '[HttpGet("/participate/karma-forge/submitted/{submissionId}")]',
                    },
                ],
            }
            completed, report = self.run_script(manifest)

        self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
        self.assertEqual(report["summary"]["failed_count"], 0)
        self.assertEqual(report["summary"]["controller_contract_count"], 2)
        self.assertEqual(
            [route["mode"] for route in report["routes"]],
            ["controller_contract", "controller_contract"],
        )

    def test_verifier_supports_public_redirect_alias_routes(self) -> None:
        manifest = {
            "surface": "chummer.run",
            "version": 1,
            "public_routes": [
                {
                    "path": "/player",
                    "audience": "public",
                    "purpose": "play_projection",
                    "requires_auth": False,
                    "guest_fallback": "/player",
                    "must_exist": True,
                    "required_redirect_location_prefix": "/mobile/player",
                }
            ],
        }

        completed, report = self.run_script(manifest)

        self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["failed_count"], 0)
        self.assertEqual(302, report["routes"][0]["status_code"])
        self.assertEqual("/mobile/player#", report["routes"][0]["redirect_location"])

    def test_alias_redirect_contract_is_exact_same_origin_and_fragment_clearing(self) -> None:
        module = load_module()
        base_url = "https://chummer.run"

        self.assertTrue(module.redirect_location_matches_exact_alias_contract(
            base_url, "/mobile/player#", "/mobile/player"))
        self.assertTrue(module.redirect_location_matches_exact_alias_contract(
            base_url, "https://chummer.run/mobile/player#", "/mobile/player"))

        rejected = [
            "/mobile/player",
            "/mobile/player#private",
            "/mobile/player?sessionId=private#",
            "/mobile/player?#",
            "/mobile/player/extra#",
            "/mobile/player-extended#",
            "/mobile/role/../player#",
            "mobile/player#",
            "//chummer.run/mobile/player#",
            "https://attacker.example/mobile/player#",
            "https://chummer.run.attacker.example/mobile/player#",
            "http://chummer.run/mobile/player#",
            "https://chummer.run:444/mobile/player#",
            "https://user:secret@chummer.run/mobile/player#",
        ]
        for location in rejected:
            with self.subTest(location=location):
                self.assertFalse(module.redirect_location_matches_exact_alias_contract(
                    base_url, location, "/mobile/player"))

    def test_public_route_verification_fails_closed_for_malicious_alias_locations(self) -> None:
        module = load_module()
        route = {
            "path": "/jammer",
            "audience": "public",
            "purpose": "play_projection",
            "requires_auth": False,
            "guest_fallback": "/jammer",
            "must_exist": True,
            "required_redirect_location_prefix": "/mobile/player",
        }
        malicious_responses = [
            (301, "/mobile/player#"),
            (303, "/mobile/player#"),
            (307, "/mobile/player#"),
            (308, "/mobile/player#"),
            (302, "/Mobile/player#"),
            (302, "/mobile/player/extra#"),
            (302, "/mobile/player?sessionId=private#"),
            (302, "https://attacker.example/mobile/player#"),
            (302, "https://chummer.run.attacker.example/mobile/player#"),
            (302, "https://user:secret@chummer.run/mobile/player#"),
            (302, "/mobile/player"),
        ]

        for status, location in malicious_responses:
            with self.subTest(status=status, location=location):
                def fake_fetch(base_url, path, **kwargs):  # noqa: ANN001, ARG001
                    return status, "", {"location": location}, f"{base_url}{path}"

                result = module.verify_route(
                    fake_fetch,
                    "https://chummer.run",
                    route,
                    public_host=None,
                    forwarded_proto=None,
                    strict_positive=False,
                    seed_receipts=False,
                    request_timeout_seconds=2,
                    max_retries=0,
                    retry_delay_seconds=0,
                )

                self.assertFalse(result.success)
                self.assertFalse(result.positive_proof)
                if status != 302:
                    self.assertIn("expected exact HTTP 302", result.detail or "")
                else:
                    self.assertIn("does not satisfy exact alias target", result.detail or "")

    def test_verifier_passes_bounded_fetch_settings_to_shared_fetch_helper(self) -> None:
        module = load_module()
        captured: dict[str, object] = {}

        def fake_fetch(base_url, path, **kwargs):
            captured["base_url"] = base_url
            captured["path"] = path
            captured["kwargs"] = kwargs
            return 200, "public", {}, f"{base_url}{path}"

        route = {
            "path": "/public",
            "audience": "public",
            "purpose": "proof_shelf",
            "requires_auth": False,
            "guest_fallback": "/public",
            "must_exist": True,
        }

        result = module.verify_route(
            fake_fetch,
            "https://example.invalid",
            route,
            public_host=None,
            forwarded_proto=None,
            strict_positive=False,
            seed_receipts=False,
            request_timeout_seconds=7.5,
            max_retries=0,
            retry_delay_seconds=0.25,
        )

        self.assertTrue(result.success)
        self.assertEqual("/public", captured["path"])
        self.assertEqual(7.5, captured["kwargs"]["request_timeout_seconds"])
        self.assertEqual(0, captured["kwargs"]["max_retries"])
        self.assertEqual(0.25, captured["kwargs"]["retry_delay_seconds"])

    def test_parse_args_accepts_bounded_worker_configuration(self) -> None:
        module = load_module()

        args = module.parse_args([
            "--base-url", "https://example.invalid",
            "--max-workers", "4",
            "--request-timeout-seconds", "3",
            "--max-retries", "0",
            "--retry-delay-seconds", "0.1",
            "--path", "/public",
            "--path", "/private",
        ])

        self.assertEqual(4, args.max_workers)
        self.assertEqual(3.0, args.request_timeout_seconds)
        self.assertEqual(0, args.max_retries)
        self.assertEqual(0.1, args.retry_delay_seconds)
        self.assertEqual(["/public", "/private"], args.path)

    def test_verifier_can_filter_to_specific_manifest_paths(self) -> None:
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
                    "required_texts": ["public"],
                },
                {
                    "path": "/private",
                    "audience": "registered",
                    "purpose": "signed_in_dashboard",
                    "requires_auth": True,
                    "guest_fallback": "/login?next=/private",
                    "must_exist": True,
                },
            ],
        }

        completed, report = self.run_script(manifest, ["--path", "/private"])

        self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["route_count"], 1)
        self.assertEqual(report["summary"]["registered_route_count"], 1)
        self.assertEqual(report["summary"]["failed_count"], 0)
        self.assertEqual(["/private"], report["path_filter"])
        self.assertEqual("/private", report["routes"][0]["path"])

    def test_local_base_urls_clamp_effective_worker_count(self) -> None:
        module = load_module()

        self.assertEqual(1, module.resolve_effective_max_workers("http://127.0.0.1:8091", 12))
        self.assertEqual(1, module.resolve_effective_max_workers("http://localhost:8091", 1))
        self.assertEqual(1, module.resolve_effective_max_workers("https://chummer.run", 12))
        self.assertEqual(1, module.resolve_effective_max_workers("https://chummer.run", 2))
        self.assertEqual(12, module.resolve_effective_max_workers("https://example.invalid", 12))

    def test_local_base_urls_floor_effective_request_timeout(self) -> None:
        module = load_module()

        self.assertEqual(12.0, module.resolve_effective_request_timeout_seconds("http://127.0.0.1:8091", 3.0))
        self.assertEqual(12.0, module.resolve_effective_request_timeout_seconds("http://localhost:8091", 12.0))
        self.assertEqual(15.0, module.resolve_effective_request_timeout_seconds("http://127.0.0.1:8091", 15.0))
        self.assertEqual(20.0, module.resolve_effective_request_timeout_seconds("https://chummer.run", 3.0))
        self.assertEqual(20.0, module.resolve_effective_request_timeout_seconds("https://chummer.run", 15.0))
        self.assertEqual(3.0, module.resolve_effective_request_timeout_seconds("https://example.invalid", 3.0))

    def test_verifier_requires_seed_receipts_for_strict_positive_parameterized_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            controller_path = temp_root / "PublicLandingController.cs"
            controller_path.write_text(
                '[HttpGet("/contact/submitted/{caseId}")]\n'
                '[HttpGet("/participate/karma-forge/submitted/{submissionId}")]\n',
                encoding="utf-8",
            )
            manifest = {
                "surface": "chummer.run",
                "version": 1,
                "public_routes": [
                    {
                        "path": "/contact/submitted/{caseId}",
                        "audience": "public",
                        "purpose": "support_submission_receipt",
                        "requires_auth": False,
                        "guest_fallback": "/contact/submitted/{caseId}",
                        "must_exist": True,
                        "verification_mode": "controller_contract",
                        "verification_file": str(controller_path),
                        "verification_pattern": '[HttpGet("/contact/submitted/{caseId}")]',
                    },
                    {
                        "path": "/participate/karma-forge/submitted/{submissionId}",
                        "audience": "public",
                        "purpose": "governed_future_signal_receipt",
                        "requires_auth": False,
                        "guest_fallback": "/participate/karma-forge/submitted/{submissionId}",
                        "must_exist": True,
                        "verification_mode": "controller_contract",
                        "verification_file": str(controller_path),
                        "verification_pattern": '[HttpGet("/participate/karma-forge/submitted/{submissionId}")]',
                    },
                ],
            }
            completed, report = self.run_script(manifest, ["--strict-positive"])

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["summary"]["failed_count"], 2)
        self.assertEqual(report["summary"]["seed_required_count"], 2)
        self.assertTrue(all(route["proof_class"] == "seed_required" for route in report["routes"]))

    def test_verifier_supports_seeded_strict_positive_receipt_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            controller_path = temp_root / "PublicLandingController.cs"
            controller_path.write_text(
                '[HttpGet("/contact/submitted/{caseId}")]\n'
                '[HttpGet("/participate/karma-forge/submitted/{submissionId}")]\n',
                encoding="utf-8",
            )
            manifest = {
                "surface": "chummer.run",
                "version": 1,
                "public_routes": [
                    {
                        "path": "/contact/submitted/{caseId}",
                        "audience": "public",
                        "purpose": "support_submission_receipt",
                        "requires_auth": False,
                        "guest_fallback": "/contact/submitted/{caseId}",
                        "must_exist": True,
                        "verification_mode": "controller_contract",
                        "verification_file": str(controller_path),
                        "verification_pattern": '[HttpGet("/contact/submitted/{caseId}")]',
                    },
                    {
                        "path": "/participate/karma-forge/submitted/{submissionId}",
                        "audience": "public",
                        "purpose": "governed_future_signal_receipt",
                        "requires_auth": False,
                        "guest_fallback": "/participate/karma-forge/submitted/{submissionId}",
                        "must_exist": True,
                        "verification_mode": "controller_contract",
                        "verification_file": str(controller_path),
                        "verification_pattern": '[HttpGet("/participate/karma-forge/submitted/{submissionId}")]',
                    },
                ],
            }
            completed, report = self.run_script(manifest, ["--strict-positive", "--seed-receipts"])

        self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["failed_count"], 0)
        self.assertEqual(report["summary"]["positive_proof_count"], 2)
        self.assertEqual(report["summary"]["seeded_receipt_count"], 2)
        self.assertTrue(all(route["proof_class"] == "receipt_route" for route in report["routes"]))
        self.assertEqual(report["summary"]["negative_path_count"], 2)
        self.assertEqual(report["summary"]["negative_path_failed_count"], 0)
        self.assertTrue(all(item["status_code"] == 404 for item in report["negative_paths"]))


if __name__ == "__main__":
    unittest.main()
