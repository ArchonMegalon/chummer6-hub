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
        lines = queue_text.splitlines(keepends=True)
        package_line_index = next(
            (index for index, line in enumerate(lines) if line.lstrip() == f"package_id: {PACKAGE_ID}\n"),
            None,
        )
        if package_line_index is None:
            raise ValueError(f"missing package_id block for {PACKAGE_ID}")

        package_start_index = package_line_index
        package_indent: int | None = None
        for index in range(package_line_index, -1, -1):
            stripped = lines[index].lstrip()
            indent = len(lines[index]) - len(stripped)
            if stripped.startswith("- title:"):
                package_start_index = index
                package_indent = indent
                break

        if package_indent is None:
            raise ValueError(f"missing title row for {PACKAGE_ID}")

        package_end_index = len(lines)
        for index in range(package_start_index + 1, len(lines)):
            stripped = lines[index].lstrip()
            if not stripped.startswith("- title:"):
                continue
            indent = len(lines[index]) - len(stripped)
            if indent == package_indent:
                package_end_index = index
                break

        start = sum(len(line) for line in lines[:package_start_index])
        end = sum(len(line) for line in lines[:package_end_index])
        return start, end

    @staticmethod
    def _canonicalize_package_block(package_block: str) -> str:
        lines = package_block.splitlines()
        suffix = "\n" if package_block.endswith("\n") else ""
        normalized_lines: list[str] = []
        for line in lines:
            if not line:
                normalized_lines.append(line)
                continue
            stripped = line.lstrip()
            if stripped.startswith("- title:"):
                normalized_lines.append(f"  {stripped}")
                continue
            if line.startswith("  - "):
                normalized_lines.append(f"      {stripped}")
                continue
            if line.startswith("    "):
                normalized_lines.append(f"  {line}")
                continue
            if line.startswith("  "):
                normalized_lines.append(f"  {line}")
                continue
            normalized_lines.append(line)
        return "\n".join(normalized_lines) + suffix

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
            package_start, package_end = self._package_block_range(source_text)
            package_block = self._canonicalize_package_block(source_text[package_start:package_end])
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
            package_start, package_end = self._package_block_range(source_text)
            package_block = self._canonicalize_package_block(source_text[package_start:package_end])
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
            package_block = self._canonicalize_package_block(source_text[start:end])
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
            package_block = self._canonicalize_package_block(source_text[start:end])
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

    def test_queue_identity_guard_rejects_second_row_claiming_owned_surfaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-surface-copy-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            start, end = self._package_block_range(source_text)
            package_block = self._canonicalize_package_block(source_text[start:end])
            duplicate_block = (
                package_block.replace(
                    f"  - title: {TITLE}\n",
                    "  - title: Reopen workspace continuity through another package\n",
                    1,
                )
                .replace(
                    f"    package_id: {PACKAGE_ID}\n",
                    "    package_id: next90-m105-hub-workspace-continuity-copy\n",
                    1,
                )
                .replace("    frontier_id: 4623636482\n", "    frontier_id: 9999999999\n", 1)
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
        self.assertIn("expected exactly one row owning surfaces", result.stderr)
        self.assertIn("workspace_restore:provenance", result.stderr)
        self.assertIn("entitlement_sync:conflict_receipts", result.stderr)

    def test_queue_identity_guard_rejects_wrong_completion_action(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-action-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            start, end = self._package_block_range(source_text)
            package_block = self._canonicalize_package_block(source_text[start:end])
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
            package_block = self._canonicalize_package_block(source_text[start:end])
            self.assertIn("    do_not_reopen_reason:", package_block)
            lines = package_block.splitlines(keepends=True)
            updated_lines: list[str] = []
            index = 0
            replaced = False
            while index < len(lines):
                line = lines[index]
                if not replaced and line.startswith("    do_not_reopen_reason:"):
                    updated_lines.append("    do_not_reopen_reason: Reopen this package whenever continuity proof looks stale.\n")
                    replaced = True
                    index += 1
                    while index < len(lines) and lines[index].startswith("      "):
                        index += 1
                    continue
                updated_lines.append(line)
                index += 1
            self.assertTrue(replaced)
            updated_block = "".join(updated_lines)
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

    def test_queue_identity_guard_rejects_task_local_telemetry_marker_in_package_block(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-telemetry-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            start, end = self._package_block_range(source_text)
            package_block = self._canonicalize_package_block(source_text[start:end])
            updated_block = package_block + "      - TASK_LOCAL_TELEMETRY.generated.json copied from a worker run\n"
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
        self.assertIn("forbidden active-run proof marker: TASK_LOCAL_TELEMETRY", result.stderr)

    def test_queue_identity_guard_rejects_active_run_handoff_marker_in_package_block(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-handoff-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            start, end = self._package_block_range(source_text)
            package_block = self._canonicalize_package_block(source_text[start:end])
            updated_block = package_block + "      - ACTIVE_RUN_HANDOFF.generated.md copied into queue proof\n"
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
        self.assertIn("forbidden active-run proof marker: ACTIVE_RUN_HANDOFF", result.stderr)

    def test_queue_identity_guard_rejects_successor_prompt_metadata_in_package_block(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-prompt-metadata-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            start, end = self._package_block_range(source_text)
            package_block = self._canonicalize_package_block(source_text[start:end])
            updated_block = package_block + "      - execution rules inside this run copied from worker prompt\n"
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
        self.assertIn("forbidden active-run proof marker: execution rules inside this run", result.stderr)

    def test_queue_identity_guard_rejects_task_local_telemetry_fields_in_package_block(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-telemetry-fields-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            start, end = self._package_block_range(source_text)
            package_block = self._canonicalize_package_block(source_text[start:end])
            updated_block = (
                package_block
                + "      - active_runs_count, eta_human, and remaining_not_started_milestones from task-local telemetry are not repo-local proof.\n"
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
        self.assertIn("forbidden active-run proof marker: active_runs_count", result.stderr)
        self.assertIn("forbidden active-run proof marker: eta_human", result.stderr)
        self.assertIn("forbidden active-run proof marker: remaining_not_started_milestones", result.stderr)

    def test_queue_identity_guard_rejects_active_run_helper_command_markers_in_package_block(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-helper-command-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            start, end = self._package_block_range(source_text)
            package_block = self._canonicalize_package_block(source_text[start:end])
            updated_block = package_block + "      - run_ooda_design_supervisor_until_quiet copied from an active-run helper command\n"
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
        self.assertIn("forbidden active-run proof marker: run_ooda_design_supervisor_until_quiet", result.stderr)

    def test_queue_identity_guard_rejects_html_encoded_active_run_markers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-html-helper-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            start, end = self._package_block_range(source_text)
            package_block = self._canonicalize_package_block(source_text[start:end])
            updated_block = package_block + "      - ACTIVE&#95;RUN&#95;HANDOFF.generated.md copied into queue proof\n"
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
        self.assertIn("forbidden active-run proof marker: ACTIVE_RUN_HANDOFF", result.stderr)

    def test_queue_identity_guard_rejects_url_encoded_active_run_markers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-url-helper-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            start, end = self._package_block_range(source_text)
            package_block = source_text[start:end]
            updated_block = package_block + "      - TASK%5FLOCAL%5FTELEMETRY.generated.json copied into queue proof\n"
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
        self.assertIn("forbidden active-run proof marker: TASK_LOCAL_TELEMETRY", result.stderr)

    def test_queue_identity_guard_rejects_hex_encoded_helper_commands(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-hex-helper-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            source_queue_path = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            source_text = source_queue_path.read_text(encoding="utf-8")
            start, end = self._package_block_range(source_text)
            package_block = source_text[start:end]
            updated_block = package_block + "      - run\\x5fooda\\x5fdesign\\x5fsupervisor\\x5funtil\\x5fquiet copied into queue proof\n"
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
        self.assertIn("forbidden active-run proof marker: run_ooda_design_supervisor_until_quiet", result.stderr)

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
                "  landed_commit: 4d4b3856\n",
                "  landed_commit: 00000000\n",
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
