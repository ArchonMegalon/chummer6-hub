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


def _append_supervisor_status_helper_proof(text: str) -> str:
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
        + "      - Supervisor status helper says the successor-wave telemetry eta is green.\n"
        + text[insert_at:]
    )


def _append_successor_telemetry_summary_proof(text: str) -> str:
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
        + "      - copied worker summary: remaining milestones 20, remaining queue items 41, critical path 101 -> 102 -> 105.\n"
        + text[insert_at:]
    )


def _append_task_local_telemetry_field_name_proof(text: str) -> str:
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
        + "      - status_query_supported: false is task-local telemetry, not M105 package proof.\n"
        + text[insert_at:]
    )


def _append_successor_frontier_detail_proof(text: str) -> str:
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
        + "      - Successor frontier detail says polling disabled and status query unsupported.\n"
        + text[insert_at:]
    )


def _append_successor_prompt_control_proof(text: str) -> str:
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
        + "      - Assigned successor queue package and successor frontier ids were copied from execution rules inside this run.\n"
        + text[insert_at:]
    )


def _append_registry_task_local_telemetry_proof(text: str) -> str:
    task_marker = "      - id: 105.1\n"
    task_index = text.find(task_marker)
    if task_index == -1:
        raise AssertionError("missing registry task block for 105.1")

    evidence_index = text.find("        evidence:\n", task_index)
    if evidence_index == -1:
        raise AssertionError("missing evidence block for 105.1")

    insert_at = evidence_index + len("        evidence:\n")
    return (
        text[:insert_at]
        + "          - TASK_LOCAL_TELEMETRY.generated.json worker-run telemetry summary is not repo-local M105 package proof.\n"
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


def _append_extra_allowed_path(text: str) -> str:
    package_marker = f"    package_id: {PACKAGE_ID}\n"
    package_index = text.find(package_marker)
    if package_index == -1:
        raise AssertionError(f"missing package row for {PACKAGE_ID}")

    marker = "    allowed_paths:\n      - Chummer.Run.Api\n      - scripts\n      - tests\n"
    path_index = text.find(marker, package_index)
    if path_index == -1:
        raise AssertionError("missing canonical allowed_paths block")

    return text[:path_index] + marker + "      - docs\n" + text[path_index + len(marker):]


def _append_extra_owned_surface(text: str) -> str:
    package_marker = f"    package_id: {PACKAGE_ID}\n"
    package_index = text.find(package_marker)
    if package_index == -1:
        raise AssertionError(f"missing package row for {PACKAGE_ID}")

    marker = (
        "    owned_surfaces:\n"
        "      - workspace_restore:provenance\n"
        "      - entitlement_sync:conflict_receipts\n"
    )
    surface_index = text.find(marker, package_index)
    if surface_index == -1:
        raise AssertionError("missing canonical owned_surfaces block")

    return text[:surface_index] + marker + "      - workspace_restore:unowned_surface\n" + text[surface_index + len(marker):]


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


def _remove_queue_scope_guard_proof(text: str) -> str:
    marker = "          - /docker/chummercomplete/chummer.run-services commit 3b854764 tightens the M105 workspace queue scope guard so completed-package proof cannot widen allowed paths or owned surfaces.\n"
    if marker not in text:
        raise AssertionError("missing queue scope guard proof floor")

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

    def test_verifier_rejects_supervisor_status_and_telemetry_helper_phrasing_as_queue_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-supervisor-helper-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "fleet-queue.yaml"
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_path.write_text(
                _append_supervisor_status_helper_proof(source_queue_path.read_text(encoding="utf-8")),
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
        self.assertIn("forbidden active-run proof marker: successor-wave telemetry", result.stderr)
        self.assertIn("forbidden active-run proof marker: supervisor status", result.stderr)
        self.assertIn("forbidden active-run proof marker: status helper", result.stderr)
        self.assertIn(PACKAGE_ID, result.stderr)

    def test_verifier_rejects_copied_successor_telemetry_summary_as_queue_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-telemetry-summary-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "fleet-queue.yaml"
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_path.write_text(
                _append_successor_telemetry_summary_proof(source_queue_path.read_text(encoding="utf-8")),
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
        self.assertIn("forbidden active-run proof marker: remaining milestones", result.stderr)
        self.assertIn("forbidden active-run proof marker: remaining queue items", result.stderr)
        self.assertIn("forbidden active-run proof marker: critical path", result.stderr)
        self.assertIn(PACKAGE_ID, result.stderr)

    def test_verifier_rejects_task_local_telemetry_field_names_as_queue_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-telemetry-field-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "fleet-queue.yaml"
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_path.write_text(
                _append_task_local_telemetry_field_name_proof(source_queue_path.read_text(encoding="utf-8")),
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
        self.assertIn("forbidden active-run proof marker: status_query_supported", result.stderr)
        self.assertIn(PACKAGE_ID, result.stderr)

    def test_verifier_rejects_successor_frontier_detail_phrasing_as_queue_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-frontier-detail-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "fleet-queue.yaml"
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_path.write_text(
                _append_successor_frontier_detail_proof(source_queue_path.read_text(encoding="utf-8")),
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
        self.assertIn("forbidden active-run proof marker: successor frontier detail", result.stderr)
        self.assertIn("forbidden active-run proof marker: polling disabled", result.stderr)
        self.assertIn("forbidden active-run proof marker: status query", result.stderr)
        self.assertIn(PACKAGE_ID, result.stderr)

    def test_verifier_rejects_copied_successor_prompt_control_phrasing_as_queue_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-prompt-control-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "fleet-queue.yaml"
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_path.write_text(
                _append_successor_prompt_control_proof(source_queue_path.read_text(encoding="utf-8")),
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
        self.assertIn("forbidden active-run proof marker: successor frontier ids", result.stderr)
        self.assertIn("forbidden active-run proof marker: assigned successor queue package", result.stderr)
        self.assertIn("forbidden active-run proof marker: execution rules inside this run", result.stderr)
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

    def test_verifier_fails_closed_when_registry_drops_queue_scope_guard_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-registry-scope-proof-") as temp_dir:
            registry_path = Path(temp_dir) / "registry.yaml"
            source_registry_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            )
            registry_path.write_text(
                _remove_queue_scope_guard_proof(source_registry_path.read_text(encoding="utf-8")),
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
        self.assertIn("commit 3b854764 tightens the M105 workspace queue scope guard", result.stderr)
        self.assertIn("105.1", result.stderr)

    def test_verifier_rejects_task_local_telemetry_as_registry_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-registry-task-telemetry-") as temp_dir:
            registry_path = Path(temp_dir) / "registry.yaml"
            source_registry_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            )
            registry_path.write_text(
                _append_registry_task_local_telemetry_proof(source_registry_path.read_text(encoding="utf-8")),
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
        self.assertIn("forbidden active-run proof marker: TASK_LOCAL_TELEMETRY", result.stderr)
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

    def test_verifier_rejects_widened_queue_allowed_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-wide-paths-") as temp_dir:
            queue_path = Path(temp_dir) / "fleet-queue.yaml"
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_path.write_text(
                _append_extra_allowed_path(source_queue_path.read_text(encoding="utf-8")),
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
        self.assertIn("allowed_paths must be exactly", result.stderr)
        self.assertIn(PACKAGE_ID, result.stderr)

    def test_verifier_rejects_widened_queue_owned_surfaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-wide-surfaces-") as temp_dir:
            queue_path = Path(temp_dir) / "fleet-queue.yaml"
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_path.write_text(
                _append_extra_owned_surface(source_queue_path.read_text(encoding="utf-8")),
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
        self.assertIn("owned_surfaces must be exactly", result.stderr)
        self.assertIn(PACKAGE_ID, result.stderr)


if __name__ == "__main__":
    unittest.main()
