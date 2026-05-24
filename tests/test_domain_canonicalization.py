from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_domain_canonicalization.py"


class _FakeResponse:
    def __init__(self, status_code: int = 200, location: str | None = None) -> None:
        self.status_code = status_code
        self.headers = {}
        if location is not None:
            self.headers["Location"] = location


def _load_module():
    scripts_dir = str(SCRIPT_PATH.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("verify_domain_canonicalization", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load verifier module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DomainCanonicalizationTests(unittest.TestCase):
    def test_verifier_prints_explicit_ok_line_on_pass(self) -> None:
        module = _load_module()
        stdout = io.StringIO()

        with (
            patch.object(module.requests, "get", return_value=_FakeResponse()),
            patch.object(module, "PUBLIC_FILES", []),
            patch.object(module, "completion_path", side_effect=lambda name: Path("/tmp") / name),
            patch.object(module, "write_json"),
            patch.object(module, "write_text"),
            patch.object(module, "now_iso", return_value="2026-05-24T00:00:00Z"),
            redirect_stdout(stdout),
        ):
            result = module.main()

        self.assertEqual(result, 0)
        self.assertIn("domain_canonicalization:ok", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
