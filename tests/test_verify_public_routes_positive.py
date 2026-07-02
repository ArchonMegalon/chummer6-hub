from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_public_routes_positive.py"


def load_module():
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("verify_public_routes_positive", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class VerifyPublicRoutesPositiveTests(unittest.TestCase):
    def test_source_verifier_reads_output_file_instead_of_stdout_only(self) -> None:
        module = load_module()
        payload = {
            "contract_name": "chummer.public_route_proof",
            "status": "pass",
            "routes": [],
        }

        def fake_run(command, cwd, text, capture_output, check):
            del cwd, text, capture_output, check
            output_path = Path(command[command.index("--output") + 1])
            output_path.write_text(json.dumps(payload), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with mock.patch.object(module.subprocess, "run", side_effect=fake_run):
            result = module.run_source_verifier("https://chummer.run")

        self.assertEqual(payload, result)


if __name__ == "__main__":
    unittest.main()
