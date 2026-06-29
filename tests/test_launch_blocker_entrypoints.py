from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DOMAIN_SCRIPT = REPO_ROOT / "scripts" / "canonical_domain_audit.py"
SUPPORT_PRIVACY_SCRIPT = REPO_ROOT / "scripts" / "support_feedback_privacy_gate.py"


class _CommandResult:
    def __init__(self, returncode: int = 0, stdout: str = "ok", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeResponse:
    def __init__(self, url: str, text: str, status_code: int = 200) -> None:
        self.url = url
        self.text = text
        self.status_code = status_code


class _FakeSession:
    def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
        del timeout, allow_redirects
        if url.endswith("/contact"):
            return _FakeResponse(url, "<main><h1>Contact</h1><p>Private account details stay out of public comments.</p></main>")
        if url.endswith("/participate"):
            return _FakeResponse(url, "<main><h1>Participate</h1><p>Public requests stay reviewed and first-party.</p></main>")
        if url.endswith("/feedback") or url.endswith("/help/feedback"):
            return _FakeResponse("https://chummer.run/participate", "<main><h1>Participate</h1><p>Public requests stay reviewed.</p></main>")
        raise AssertionError(f"unexpected url {url}")


def _load_module(path: Path, module_name: str):
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LaunchBlockerEntrypointTests(unittest.TestCase):
    def test_canonical_domain_audit_composes_existing_domain_and_origin_gates(self) -> None:
        module = _load_module(CANONICAL_DOMAIN_SCRIPT, "canonical_domain_audit")
        stdout = io.StringIO()

        with (
            patch.object(module.subprocess, "run", return_value=_CommandResult()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json"),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-06-29T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.main()

        self.assertEqual(result, 0)
        self.assertIn("canonical_domain_audit:ok", stdout.getvalue())

    def test_canonical_domain_audit_fails_when_a_child_gate_fails(self) -> None:
        module = _load_module(CANONICAL_DOMAIN_SCRIPT, "canonical_domain_audit_fail")

        with (
            patch.object(module.subprocess, "run", side_effect=[_CommandResult(), _CommandResult(returncode=1, stderr="origin down")]),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json"),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-06-29T00:00:00Z"),
        ):
            result = module.main()

        self.assertEqual(result, 1)

    def test_support_feedback_privacy_gate_accepts_first_party_routes(self) -> None:
        module = _load_module(SUPPORT_PRIVACY_SCRIPT, "support_feedback_privacy_gate")
        stdout = io.StringIO()

        with (
            patch.object(module.requests, "Session", return_value=_FakeSession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json"),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-06-29T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.run("https://chummer.run")

        self.assertEqual(result, 0)
        self.assertIn("support_feedback_privacy_gate:ok", stdout.getvalue())

    def test_support_feedback_privacy_gate_fails_on_provider_leak(self) -> None:
        module = _load_module(SUPPORT_PRIVACY_SCRIPT, "support_feedback_privacy_gate_fail")

        class LeakySession(_FakeSession):
            def get(self, url: str, timeout: int = 30, allow_redirects: bool = True) -> _FakeResponse:
                response = super().get(url, timeout=timeout, allow_redirects=allow_redirects)
                if url.endswith("/participate"):
                    return _FakeResponse(response.url, "<main><h1>Participate</h1><p>ProductLift provider callback</p></main>")
                return response

        with (
            patch.object(module.requests, "Session", return_value=LeakySession()),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json"),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-06-29T00:00:00Z"),
        ):
            result = module.run("https://chummer.run")

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
