from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_workspace_restore_receipts.py"
PACKAGE_ID = "next90-m105-hub-workspace-continuity"


def _remove_package_frontier_id(text: str) -> str:
    package_marker = f"    package_id: {PACKAGE_ID}\n"
    package_index = text.find(package_marker)
    if package_index == -1:
        raise AssertionError(f"missing package row for {PACKAGE_ID}")

    next_package_index = text.find("\n  - title:", package_index + len(package_marker))
    if next_package_index == -1:
        next_package_index = len(text)

    before = text[:package_index]
    package_block = text[package_index:next_package_index]
    after = text[next_package_index:]
    return before + package_block.replace("    frontier_id: 4623636482\n", "", 1) + after


class WorkspaceRestoreQueueFrontierGuardTests(unittest.TestCase):
    def test_verifier_fails_closed_when_fleet_queue_drops_frontier_id(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-fleet-frontier-") as temp_dir:
            queue_path = Path(temp_dir) / "fleet-queue.yaml"
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_path.write_text(
                _remove_package_frontier_id(source_queue_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_QUEUE_STAGING"] = str(queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("frontier_id: 4623636482", result.stderr)
        self.assertIn(PACKAGE_ID, result.stderr)

    def test_verifier_fails_closed_when_design_queue_drops_frontier_id(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-design-frontier-") as temp_dir:
            queue_path = Path(temp_dir) / "design-queue.yaml"
            source_queue_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_path.write_text(
                _remove_package_frontier_id(source_queue_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_DESIGN_QUEUE_STAGING"] = str(queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("frontier_id: 4623636482", result.stderr)
        self.assertIn(PACKAGE_ID, result.stderr)


if __name__ == "__main__":
    unittest.main()
