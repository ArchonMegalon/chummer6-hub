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


def _append_mixed_case_forbidden_proof_marker(text: str) -> str:
    package_marker = f"    package_id: {PACKAGE_ID}\n"
    package_index = text.find(package_marker)
    if package_index == -1:
        raise AssertionError(f"missing package row for {PACKAGE_ID}")

    proof_index = text.find("    proof:\n", package_index)
    if proof_index == -1:
        raise AssertionError(f"missing proof row for {PACKAGE_ID}")

    insert_at = proof_index + len("    proof:\n")
    return (
        text[:insert_at]
        + "      - Mixed-case Active-Run Helper output is not valid package proof.\n"
        + text[insert_at:]
    )


def _append_active_run_handoff_path(text: str) -> str:
    package_marker = f"    package_id: {PACKAGE_ID}\n"
    package_index = text.find(package_marker)
    if package_index == -1:
        raise AssertionError(f"missing package row for {PACKAGE_ID}")

    proof_index = text.find("    proof:\n", package_index)
    if proof_index == -1:
        raise AssertionError(f"missing proof row for {PACKAGE_ID}")

    insert_at = proof_index + len("    proof:\n")
    return (
        text[:insert_at]
        + "      - /var/lib/codex-fleet/chummer_design_supervisor/shard-5/ACTIVE_RUN_HANDOFF.generated.md\n"
        + text[insert_at:]
    )


def _duplicate_package_row(text: str) -> str:
    package_marker = f"    package_id: {PACKAGE_ID}\n"
    package_index = text.find(package_marker)
    if package_index == -1:
        raise AssertionError(f"missing package row for {PACKAGE_ID}")

    start = text.rfind("\n  - title:", 0, package_index)
    if start == -1:
        raise AssertionError(f"missing package title row for {PACKAGE_ID}")
    start += 1

    end = text.find("\n  - title:", package_index + len(package_marker))
    if end == -1:
        end = len(text)

    package_block = text[start:end]
    return text[:end] + "\n" + package_block + text[end:]


def _remove_current_queue_frontier_proof(text: str) -> str:
    marker = "          - /docker/chummercomplete/chummer.run-services commit e0d2bff6 pins the M105 workspace queue-frontier guard proof.\n"
    if marker not in text:
        raise AssertionError("missing current queue-frontier proof floor")

    return text.replace(marker, "", 1)


def _remove_package_scoped_receipt_proof(text: str) -> str:
    marker = "      - /docker/chummercomplete/chummer.run-services commit 9f425d04 tightens M105 package-scoped receipt proof so untracked workspace continuity receipt rows cannot hide beside the canonical receipts.\n"
    if marker not in text:
        raise AssertionError("missing package-scoped receipt proof floor")

    return text.replace(marker, "", 1)


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

    def test_verifier_rejects_forbidden_queue_proof_markers_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-forbidden-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "fleet-queue.yaml"
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_path.write_text(
                _append_mixed_case_forbidden_proof_marker(source_queue_path.read_text(encoding="utf-8")),
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
        self.assertIn("forbidden active-run proof marker: active-run helper", result.stderr)
        self.assertIn(PACKAGE_ID, result.stderr)

    def test_verifier_rejects_active_run_handoff_paths_as_queue_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-handoff-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "fleet-queue.yaml"
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_path.write_text(
                _append_active_run_handoff_path(source_queue_path.read_text(encoding="utf-8")),
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
        self.assertIn("forbidden active-run proof marker: ACTIVE_RUN_HANDOFF", result.stderr)
        self.assertIn("forbidden active-run proof marker: /var/lib/codex-fleet", result.stderr)
        self.assertIn(PACKAGE_ID, result.stderr)

    def test_verifier_rejects_blocked_ooda_helper_command_names_as_queue_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-ooda-helper-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "fleet-queue.yaml"
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_path.write_text(
                source_queue_path.read_text(encoding="utf-8").replace(
                    "      - python3 scripts/verify_workspace_restore_receipts.py\n",
                    "      - run_ooda_design_supervisor_until_quiet.py output from an active worker run\n"
                    "      - python3 scripts/verify_workspace_restore_receipts.py\n",
                    1,
                ),
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
        self.assertIn("forbidden active-run proof marker: run_ooda_design_supervisor_until_quiet", result.stderr)
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

    def test_verifier_fails_closed_when_registry_drops_current_queue_frontier_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-registry-current-proof-") as temp_dir:
            registry_path = Path(temp_dir) / "registry.yaml"
            source_registry_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            )
            registry_path.write_text(
                _remove_current_queue_frontier_proof(source_registry_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_REGISTRY"] = str(registry_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("commit e0d2bff6 pins the M105 workspace queue-frontier guard proof", result.stderr)
        self.assertIn("105.1", result.stderr)

    def test_verifier_fails_closed_when_registry_drops_package_scoped_receipt_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-registry-receipt-proof-") as temp_dir:
            registry_path = Path(temp_dir) / "registry.yaml"
            source_registry_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            )
            registry_path.write_text(
                _remove_package_scoped_receipt_proof(source_registry_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_REGISTRY"] = str(registry_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("commit 9f425d04 tightens M105 package-scoped receipt proof", result.stderr)
        self.assertIn("105.1", result.stderr)

    def test_verifier_fails_closed_when_fleet_and_design_queue_rows_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-drift-") as temp_dir:
            queue_path = Path(temp_dir) / "fleet-queue.yaml"
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_path.write_text(
                source_queue_path.read_text(encoding="utf-8").replace(
                    "      - /docker/chummercomplete/chummer.run-services/scripts/materialize_hub_local_release_proof.py\n",
                    "      - /docker/chummercomplete/chummer.run-services/scripts/materialize_hub_local_release_proof.py\n"
                    "      - /docker/chummercomplete/chummer.run-services/tests/test_workspace_restore_queue_frontier_guard.py\n",
                    1,
                ),
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
        self.assertIn("must match", result.stderr)
        self.assertIn("NEXT_90_DAY_QUEUE_STAGING.generated.yaml", result.stderr)
        self.assertIn(PACKAGE_ID, result.stderr)

    def test_verifier_rejects_duplicate_completed_queue_rows(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-duplicate-queue-") as temp_dir:
            queue_path = Path(temp_dir) / "fleet-queue.yaml"
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_path.write_text(
                _duplicate_package_row(source_queue_path.read_text(encoding="utf-8")),
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
        self.assertIn("expected exactly one queue package block", result.stderr)
        self.assertIn(PACKAGE_ID, result.stderr)


if __name__ == "__main__":
    unittest.main()
