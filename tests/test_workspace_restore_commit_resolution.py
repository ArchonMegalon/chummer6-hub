from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_workspace_restore_receipts.py"


class WorkspaceRestoreCommitResolutionTests(unittest.TestCase):
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
