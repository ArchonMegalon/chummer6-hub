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
    @staticmethod
    def _package_block_range(queue_text: str) -> tuple[int, int]:
        package_marker = f"    package_id: {PACKAGE_ID}\n"
        package_index = queue_text.find(package_marker)
        package_start = queue_text.rfind("\n  - title:", 0, package_index) + 1
        package_end = queue_text.find("\n  - title:", package_index)
        if package_end == -1:
            package_end = len(queue_text)
        return package_start, package_end

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

    def test_queue_identity_guard_rejects_widened_allowed_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-paths-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            start, end = self._package_block_range(source_text)
            package_block = source_text[start:end]
            updated_block = package_block.replace(
                "    allowed_paths:\n"
                "      - Chummer.Run.Api\n"
                "      - scripts\n"
                "      - tests\n",
                "    allowed_paths:\n"
                "      - Chummer.Run.Api\n"
                "      - scripts\n"
                "      - tests\n"
                "      - docs\n",
                1,
            )
            queue_path.write_text(source_text[:start] + updated_block + source_text[end:], encoding="utf-8")

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
        self.assertIn(f"{PACKAGE_ID}.allowed_paths must be exactly", result.stderr)

    def test_queue_identity_guard_rejects_drifted_owned_surfaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-surfaces-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            start, end = self._package_block_range(source_text)
            package_block = source_text[start:end]
            updated_block = package_block.replace("      - entitlement_sync:conflict_receipts", "", 1)
            queue_path.write_text(source_text[:start] + updated_block + source_text[end:], encoding="utf-8")

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
        self.assertIn(f"{PACKAGE_ID}.owned_surfaces must be exactly", result.stderr)

    def test_queue_identity_guard_rejects_wrong_completion_action(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-action-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            start, end = self._package_block_range(source_text)
            package_block = source_text[start:end]
            updated_block = package_block.replace(
                "    completion_action: verify_closed_package_only\n",
                "    completion_action: reopen_package\n",
                1,
            )
            queue_path.write_text(source_text[:start] + updated_block + source_text[end:], encoding="utf-8")

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
        self.assertIn(f"{PACKAGE_ID}.completion_action must be 'verify_closed_package_only'", result.stderr)

    def test_queue_identity_guard_rejects_wrong_do_not_reopen_reason(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-reason-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            start, end = self._package_block_range(source_text)
            package_block = source_text[start:end]
            updated_block = package_block.replace(
                "    do_not_reopen_reason: M105 chummer6-hub workspace continuity is complete; future shards must verify the workspace restore receipt, registry row, queue row, and design-queue row instead of reopening the workspace restore and entitlement conflict receipt package.\n",
                "    do_not_reopen_reason: Reopen this package whenever continuity proof looks stale.\n",
                1,
            )
            queue_path.write_text(source_text[:start] + updated_block + source_text[end:], encoding="utf-8")

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
        self.assertIn(f"{PACKAGE_ID}.do_not_reopen_reason must be", result.stderr)

    def test_queue_identity_guard_rejects_design_queue_drift_when_fleet_queue_stays_canonical(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-design-drift-") as temp_dir:
            fleet_queue_path = Path(temp_dir) / "fleet-queue.yaml"
            design_queue_path = Path(temp_dir) / "design-queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            fleet_queue_path.write_text(source_text, encoding="utf-8")

            start, end = self._package_block_range(source_text)
            package_block = source_text[start:end]
            drifted_block = package_block.replace(
                "    landed_commit: 4d4b3856\n",
                "    landed_commit: 00000000\n",
                1,
            )
            self.assertNotEqual(package_block, drifted_block)
            design_queue_path.write_text(source_text[:start] + drifted_block + source_text[end:], encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_QUEUE_IDENTITY_FLEET_QUEUE"] = str(fleet_queue_path)
            env["CHUMMER_WORKSPACE_RESTORE_QUEUE_IDENTITY_DESIGN_QUEUE"] = str(design_queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"{PACKAGE_ID}.landed_commit must be '4d4b3856'", result.stderr)
        self.assertIn(f"{fleet_queue_path}:{PACKAGE_ID} must match {design_queue_path}:{PACKAGE_ID}", result.stderr)


if __name__ == "__main__":
    unittest.main()
