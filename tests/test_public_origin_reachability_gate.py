from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_public_origin_reachability.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_public_origin_reachability", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PublicOriginReachabilityGateTests(unittest.TestCase):
    def test_detects_cloudflare_1033_as_fail_closed(self) -> None:
        module = load_module()

        result = module.verify_public_origin.__globals__["ReachabilityResult"](
            status="fail",
            base_url="https://chummer.run/",
            final_url="https://chummer.run/",
            http_status=530,
            cloudflare_ray="ray",
            server="cloudflare",
            detected_error_code="1033",
            failure_reason="cloudflare_tunnel_unresolvable",
            generated_at="2026-06-09T00:00:00Z",
            body_excerpt="Error 1033 Cloudflare Tunnel error",
        )
        self.assertEqual(result.detected_error_code, "1033")
        self.assertEqual(result.failure_reason, "cloudflare_tunnel_unresolvable")

    def test_failure_detector_flags_1033_response(self) -> None:
        module = load_module()
        code, reason = module.detect_failure_reason(
            530,
            "Error 1033 Ray ID: x Cloudflare Tunnel error",
            {"server": "cloudflare"},
        )
        self.assertEqual(code, "1033")
        self.assertEqual(reason, "cloudflare_tunnel_unresolvable")

    def test_failure_detector_accepts_chummer_html(self) -> None:
        module = load_module()
        code, reason = module.detect_failure_reason(
            200,
            "<!doctype html><html><head><title>Chummer</title></head><body>Chummer</body></html>",
            {"server": "cloudflare"},
        )
        self.assertIsNone(code)
        self.assertIsNone(reason)

    def test_main_writes_receipt_and_fails_on_1033(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "receipt.json"
            script = f"""
import importlib.util
import json
from pathlib import Path
spec = importlib.util.spec_from_file_location("gate", r"{SCRIPT_PATH}")
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.fetch_public_origin = lambda url: (
    530,
    url,
    {{"server": "cloudflare", "cf-ray": "test-ray"}},
    b"Error 1033 Ray ID: test Cloudflare Tunnel error"
)
raise SystemExit(module.main(["--base-url", "https://chummer.run/", "--output", r"{output_path}"]))
"""
            result = subprocess.run(["python3", "-c", script], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "fail")
            self.assertEqual(payload["detected_error_code"], "1033")


if __name__ == "__main__":
    unittest.main()
