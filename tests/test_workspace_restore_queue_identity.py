from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_workspace_restore_queue_identity.py"
PACKAGE_ID = "next90-m105-hub-workspace-continuity"
TITLE = "Emit provenance and conflict receipts for workspace restore and continuity"


class WorkspaceRestoreQueueIdentityTests(unittest.TestCase):
    def test_queue_identity_guard_passes_current_fleet_and_design_rows(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("workspace restore queue identity proof passed", result.stdout)

    def test_queue_identity_guard_rejects_duplicate_title_with_different_package_id(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-identity-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            package_marker = f"    package_id: {PACKAGE_ID}\n"
            package_start = source_text.rfind("\n  - title:", 0, source_text.find(package_marker)) + 1
            package_end = source_text.find("\n  - title:", source_text.find(package_marker))
            package_block = source_text[package_start:package_end]
            duplicate_block = package_block.replace(
                f"    package_id: {PACKAGE_ID}\n",
                "    package_id: next90-m105-hub-workspace-continuity-copy\n",
                1,
            ).replace(
                "    frontier_id: 4623636482\n",
                "    frontier_id: 4623636482\n",
                1,
            )
            queue_path.write_text(source_text + duplicate_block, encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_QUEUE_IDENTITY_FLEET_QUEUE"] = str(queue_path)
            env["CHUMMER_WORKSPACE_RESTORE_QUEUE_IDENTITY_DESIGN_QUEUE"] = str(queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"expected exactly one title {TITLE!r}; found 2", result.stderr)
        self.assertIn("expected exactly one frontier_id 4623636482; found 2", result.stderr)

    def test_queue_identity_guard_rejects_frontier_on_wrong_row(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-frontier-copy-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            package_marker = f"    package_id: {PACKAGE_ID}\n"
            package_start = source_text.rfind("\n  - title:", 0, source_text.find(package_marker)) + 1
            package_end = source_text.find("\n  - title:", source_text.find(package_marker))
            package_block = source_text[package_start:package_end]
            duplicate_block = package_block.replace(
                f"  - title: {TITLE}\n",
                "  - title: Copied workspace continuity closure row\n",
                1,
            ).replace(
                f"    package_id: {PACKAGE_ID}\n",
                "    package_id: next90-m105-hub-workspace-continuity-copy\n",
                1,
            )
            queue_path.write_text(source_text + duplicate_block, encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_QUEUE_IDENTITY_FLEET_QUEUE"] = str(queue_path)
            env["CHUMMER_WORKSPACE_RESTORE_QUEUE_IDENTITY_DESIGN_QUEUE"] = str(queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected exactly one frontier_id 4623636482; found 2", result.stderr)


if __name__ == "__main__":
    unittest.main()
