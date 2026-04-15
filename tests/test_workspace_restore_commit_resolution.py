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
        self.assertIn('"5bf1a11e"', script_text)
        self.assertIn('"db002589"', script_text)
        self.assertIn('"f6db9d91"', script_text)
        self.assertIn('"b1270fd0"', script_text)
        self.assertIn('"691c625f"', script_text)
        self.assertIn('"f8226de9"', script_text)
        self.assertIn('"f8f3ce8e"', script_text)
        self.assertIn('"70b6f382"', script_text)
        self.assertIn('"0014a763"', script_text)
        self.assertIn('"d26e961c"', script_text)
        self.assertIn('"9f723c15"', script_text)
        self.assertIn('"7e908447"', script_text)
        self.assertIn('"2df21683"', script_text)
        self.assertIn('"442c76c2"', script_text)
        self.assertIn("commit fcdd1fa5 pins the current M105 workspace proof floor", script_text)
        self.assertIn("commit 021de48a requires the current M105 queue proof guard", script_text)
        self.assertIn("commit 5bf1a11e pins the current M105 workspace queue guard", script_text)
        self.assertIn("commit db002589 pins the M105 workspace queue guard proof", script_text)
        self.assertIn("commit f6db9d91 pins the M105 workspace proof floor", script_text)
        self.assertIn("commit b1270fd0 pins the M105 workspace verifier", script_text)
        self.assertIn("commit 691c625f requires the current M105 workspace proof floor", script_text)
        self.assertIn("commit f8226de9 pins the M105 workspace proof floor", script_text)
        self.assertIn("commit f8f3ce8e requires the latest M105 workspace proof floor", script_text)
        self.assertIn("commit 70b6f382 tightens the M105 served workspace proof guard", script_text)
        self.assertIn("commit 0014a763 tightens the M105 active-run proof marker guard", script_text)
        self.assertIn("commit d26e961c tightens the M105 workspace release proof guard", script_text)
        self.assertIn("commit 9f723c15 tightens the M105 queue mirror guard", script_text)
        self.assertIn("commit 7e908447 tightens the M105 workspace receipt proof", script_text)
        self.assertIn("commit 2df21683 pins the M105 workspace receipt proof floor", script_text)
        self.assertIn("commit 442c76c2 pins the M105 workspace receipt guard floor", script_text)

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
