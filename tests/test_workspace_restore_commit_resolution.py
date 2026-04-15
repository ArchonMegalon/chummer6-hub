from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_workspace_restore_receipts.py"


class WorkspaceRestoreCommitResolutionTests(unittest.TestCase):
    def test_default_required_commits_include_closed_package_hardening_commit(self) -> None:
        script_text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('"80454b41"', script_text)
        self.assertIn('"e1f65c8b"', script_text)
        self.assertIn('"b72eaf89"', script_text)
        self.assertIn('"290ec61e"', script_text)
        self.assertIn('"1d11729a"', script_text)
        self.assertIn('"35db07af"', script_text)
        self.assertIn('"784fbcef"', script_text)
        self.assertIn('"5c8e5527"', script_text)
        self.assertIn('"bd398493"', script_text)
        self.assertIn('"a45d9e9e"', script_text)
        self.assertIn('"717af57e"', script_text)
        self.assertIn('"346c3ede"', script_text)
        self.assertIn('"8d59d95f"', script_text)
        self.assertIn('"1b8d9363"', script_text)
        self.assertIn('"e0521ca5"', script_text)
        self.assertIn('"06e2ec99"', script_text)
        self.assertIn('"cb560573"', script_text)
        self.assertIn('"7c92635e"', script_text)
        self.assertIn('"c90d02e0"', script_text)
        self.assertIn('"211ce4a1"', script_text)
        self.assertIn('"93182934"', script_text)
        self.assertIn('"021de48a"', script_text)
        self.assertIn("commit fcdd1fa5 pins the current M105 workspace proof floor", script_text)
        self.assertIn("commit 021de48a requires the current M105 queue proof guard", script_text)

    def test_verifier_fails_closed_when_required_local_commit_does_not_resolve(self) -> None:
        env = os.environ.copy()
        env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_REQUIRED_COMMITS"] = "4d4b3856,00000000"

        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required local commit does not resolve: 00000000", result.stderr)


if __name__ == "__main__":
    unittest.main()
