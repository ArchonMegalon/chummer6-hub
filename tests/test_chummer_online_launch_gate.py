from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_chummer_online_launch.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_chummer_online_launch", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ChummerOnlineLaunchGateTests(unittest.TestCase):
    def test_builds_first_party_character_roster_launch_url(self) -> None:
        module = load_module()

        self.assertEqual(
            "https://chummer.run/app?command=character_roster",
            module.build_launch_url("https://chummer.run/"),
        )

    def test_classifies_blazor_roster_shell_as_pass(self) -> None:
        module = load_module()

        has_blazor, has_roster, reason = module.classify_response(
            200,
            b'<!doctype html><script src="_framework/blazor.web.js"></script><body>character_roster</body>',
        )

        self.assertTrue(has_blazor)
        self.assertTrue(has_roster)
        self.assertIsNone(reason)

    def test_rejects_redirected_character_roster_launch_without_roster_menu_markers(self) -> None:
        module = load_module()

        has_blazor, has_roster, reason = module.classify_response(
            200,
            (
                b'<!doctype html><html><head><base href="/blazor/" />'
                b'<link rel="manifest" href="manifest.webmanifest">'
                b'<script src="https://app.rybbit.io/api/script.js"></script>'
                b'</head><body><script src="_framework/blazor.web.js"></script>'
                b'<script>window.chummerPwa = window.chummerPwa || {};</script></body></html>'
            ),
            final_url="https://chummer.run/blazor/app?command=character_roster",
        )

        self.assertTrue(has_blazor)
        self.assertFalse(has_roster)
        self.assertEqual("missing_roster_menu_markers", reason)

    def test_classifies_redirected_non_roster_blazor_launch_shell_as_pass(self) -> None:
        module = load_module()

        has_blazor, has_roster, reason = module.classify_response(
            200,
            (
                b'<!doctype html><html><head><base href="/blazor/" />'
                b'<link rel="manifest" href="manifest.webmanifest">'
                b'<script src="https://app.rybbit.io/api/script.js"></script>'
                b'</head><body><script src="_framework/blazor.web.js"></script>'
                b'<script>window.chummerPwa = window.chummerPwa || {};</script></body></html>'
            ),
            final_url="https://chummer.run/blazor/app?command=new_character",
        )

        self.assertTrue(has_blazor)
        self.assertFalse(has_roster)
        self.assertIsNone(reason)

    def test_rejects_redirected_non_launch_blazor_shell_without_roster_marker(self) -> None:
        module = load_module()

        _, has_roster, reason = module.classify_response(
            200,
            (
                b'<!doctype html><html><head><base href="/blazor/" />'
                b'<link rel="manifest" href="manifest.webmanifest">'
                b'<script src="https://app.rybbit.io/api/script.js"></script>'
                b'</head><body><script src="_framework/blazor.web.js"></script>'
                b'<script>window.chummerPwa = window.chummerPwa || {};</script></body></html>'
            ),
            final_url="https://chummer.run/blazor/library",
        )

        self.assertFalse(has_roster)
        self.assertEqual("missing_roster_marker", reason)

    def test_rejects_missing_app_route_404(self) -> None:
        module = load_module()

        has_blazor, has_roster, reason = module.classify_response(404, b"404 not found")

        self.assertFalse(has_blazor)
        self.assertFalse(has_roster)
        self.assertEqual("http_404", reason)

    def test_rejects_browser_surface_fallback(self) -> None:
        module = load_module()

        _, _, reason = module.classify_response(
            200,
            b"<html><body>Browser preview is not ready right now. Download Chummer</body></html>",
        )

        self.assertEqual("browser_surface_fallback", reason)

    def test_main_writes_fail_closed_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "receipt.json"
            script = f"""
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location("gate", r"{SCRIPT_PATH}")
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.fetch_url = lambda url: (404, url, b"404 not found")
raise SystemExit(module.main(["--base-url", "https://chummer.run/", "--output", r"{output_path}"]))
"""
            result = subprocess.run(["python3", "-c", script], capture_output=True, text=True)

            self.assertEqual(result.returncode, 1)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("chummer.online_character_roster_launch.v1", payload["contractName"])
            self.assertEqual("fail", payload["status"])
            self.assertEqual("http_404", payload["failure_reason"])
            self.assertEqual("https://chummer.run/app?command=character_roster", payload["launch_url"])


if __name__ == "__main__":
    unittest.main()
