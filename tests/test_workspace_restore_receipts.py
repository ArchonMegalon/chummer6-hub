from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_workspace_restore_receipts.py"


class WorkspaceRestoreReceiptProofTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_receipt_contract(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("workspace restore receipt proof passed", result.stdout)

    def test_verifier_fails_closed_when_proof_drops_recovery_hint_marker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            proof_path = temp_root / "proof.json"
            source_proof_path = REPO_ROOT / ".codex-studio" / "published" / "HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json"
            payload = json.loads(source_proof_path.read_text(encoding="utf-8"))

            recover_markers = payload["required_markers"]["campaign_session_recover_recap"]
            payload["required_markers"]["campaign_session_recover_recap"] = [
                marker
                for marker in recover_markers
                if marker != "!string.IsNullOrWhiteSpace(item.RecoveryHint)"
            ]
            proof_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_PROOF"] = str(proof_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("!string.IsNullOrWhiteSpace(item.RecoveryHint)", result.stderr)

    def test_verifier_fails_closed_when_queue_staging_drops_complete_status(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-") as temp_dir:
            temp_root = Path(temp_dir)
            queue_path = temp_root / "queue.yaml"
            design_queue_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            registry_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            )
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_text = source_queue_path.read_text(encoding="utf-8")
            queue_text = queue_text.replace(
                "    package_id: next90-m105-hub-workspace-continuity\n"
                "    frontier_id: 4623636482\n"
                "    milestone_id: 105\n"
                "    wave: W8\n"
                "    repo: chummer6-hub\n"
                "    status: complete\n",
                "    package_id: next90-m105-hub-workspace-continuity\n"
                "    frontier_id: 4623636482\n"
                "    milestone_id: 105\n"
                "    wave: W8\n"
                "    repo: chummer6-hub\n",
            )
            queue_path.write_text(queue_text, encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_REGISTRY"] = str(registry_path)
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_QUEUE_STAGING"] = str(queue_path)
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_DESIGN_QUEUE_STAGING"] = str(design_queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("next90-m105-hub-workspace-continuity", result.stderr)
        self.assertIn("status: complete", result.stderr)

    def test_verifier_fails_closed_when_queue_staging_widens_allowed_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-paths-") as temp_dir:
            temp_root = Path(temp_dir)
            queue_path = temp_root / "queue.yaml"
            design_queue_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            registry_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            )
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_text = source_queue_path.read_text(encoding="utf-8").replace(
                "    allowed_paths:\n"
                "      - Chummer.Run.Api\n"
                "      - scripts\n"
                "      - tests\n"
                "    owned_surfaces:\n"
                "      - workspace_restore:provenance\n"
                "      - entitlement_sync:conflict_receipts\n",
                "    allowed_paths:\n"
                "      - Chummer.Run.Api\n"
                "      - scripts\n"
                "      - tests\n"
                "      - docs\n"
                "    owned_surfaces:\n"
                "      - workspace_restore:provenance\n"
                "      - entitlement_sync:conflict_receipts\n",
                1,
            )
            queue_path.write_text(queue_text, encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_REGISTRY"] = str(registry_path)
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_QUEUE_STAGING"] = str(queue_path)
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_DESIGN_QUEUE_STAGING"] = str(design_queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("allowed_paths", result.stderr)
        self.assertIn("Chummer.Run.Api", result.stderr)

    def test_verifier_fails_closed_when_queue_staging_drops_dotnet_restore_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-queue-dotnet-") as temp_dir:
            temp_root = Path(temp_dir)
            queue_path = temp_root / "queue.yaml"
            design_queue_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            registry_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            )
            source_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            queue_text = source_queue_path.read_text(encoding="utf-8").replace(
                '      - dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "CampaignSpineRestoreReceiptTests|CampaignWorkspaceServerPlaneServiceTests|CampaignOsLocalProofMaterializerTests" --no-restore\n',
                "",
                1,
            )
            queue_path.write_text(queue_text, encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_REGISTRY"] = str(registry_path)
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_QUEUE_STAGING"] = str(queue_path)
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_DESIGN_QUEUE_STAGING"] = str(design_queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CampaignSpineRestoreReceiptTests", result.stderr)
        self.assertIn("CampaignWorkspaceServerPlaneServiceTests", result.stderr)
        self.assertIn("CampaignOsLocalProofMaterializerTests", result.stderr)

    def test_verifier_fails_closed_when_registry_drops_landed_commit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-registry-") as temp_dir:
            temp_root = Path(temp_dir)
            registry_path = temp_root / "registry.yaml"
            fleet_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            design_queue_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            source_registry_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            )
            registry_text = source_registry_path.read_text(encoding="utf-8").replace(
                "        landed_commit: 4d4b3856\n",
                "",
                1,
            )
            registry_path.write_text(registry_text, encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_REGISTRY"] = str(registry_path)
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_QUEUE_STAGING"] = str(fleet_queue_path)
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_DESIGN_QUEUE_STAGING"] = str(design_queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("105.1", result.stderr)
        self.assertIn("landed_commit: 4d4b3856", result.stderr)

    def test_verifier_fails_closed_when_registry_drops_release_proof_guard_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-registry-") as temp_dir:
            temp_root = Path(temp_dir)
            registry_path = temp_root / "registry.yaml"
            fleet_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            design_queue_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            source_registry_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            )
            registry_text = source_registry_path.read_text(encoding="utf-8").replace(
                "          - /docker/chummercomplete/chummer.run-services commit b39147dc tightens the workspace restore verifier so Hub local release proof must retain the next90-m105-hub-workspace-continuity package, frontier id 4623636482, /home/work and /account/work routes, and both workspace_restore:provenance and entitlement_sync:conflict_receipts receipts.\n",
                "",
                1,
            )
            registry_path.write_text(registry_text, encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_REGISTRY"] = str(registry_path)
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_QUEUE_STAGING"] = str(fleet_queue_path)
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_DESIGN_QUEUE_STAGING"] = str(design_queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("105.1", result.stderr)
        self.assertIn("commit b39147dc tightens the workspace restore verifier", result.stderr)

    def test_verifier_fails_closed_when_design_queue_staging_drops_package(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-design-queue-") as temp_dir:
            temp_root = Path(temp_dir)
            design_queue_path = temp_root / "design-queue.yaml"
            fleet_queue_path = Path(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            registry_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            )
            source_design_queue_path = Path(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            )
            design_queue_text = source_design_queue_path.read_text(encoding="utf-8").replace(
                "    package_id: next90-m105-hub-workspace-continuity\n",
                "    package_id: next90-m105-hub-workspace-continuity-removed\n",
            )
            design_queue_path.write_text(design_queue_text, encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_REGISTRY"] = str(registry_path)
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_QUEUE_STAGING"] = str(fleet_queue_path)
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_DESIGN_QUEUE_STAGING"] = str(design_queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing queue package block", result.stderr)
        self.assertIn("next90-m105-hub-workspace-continuity", result.stderr)

    def test_verifier_fails_closed_when_local_release_proof_drops_conflict_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-release-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            release_proof_path = temp_root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            source_release_proof_path = REPO_ROOT / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            payload = json.loads(source_release_proof_path.read_text(encoding="utf-8"))
            payload["proof_receipts"] = [
                receipt
                for receipt in payload["proof_receipts"]
                if receipt.get("receipt_id") != "entitlement_sync:conflict_receipts"
            ]
            release_proof_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_LOCAL_RELEASE_PROOF"] = str(release_proof_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("proof_receipts missing entitlement_sync:conflict_receipts", result.stderr)

    def test_verifier_fails_closed_when_local_release_proof_drops_recoverable_conflict_summary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-release-summary-") as temp_dir:
            temp_root = Path(temp_dir)
            release_proof_path = temp_root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            source_release_proof_path = REPO_ROOT / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            payload = json.loads(source_release_proof_path.read_text(encoding="utf-8"))
            for receipt in payload["proof_receipts"]:
                if receipt.get("receipt_id") == "entitlement_sync:conflict_receipts":
                    receipt["summary"] = "Entitlement sync emits conflict receipts."
            release_proof_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_LOCAL_RELEASE_PROOF"] = str(release_proof_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("entitlement_sync:conflict_receipts.summary missing", result.stderr)
        self.assertIn("continue-blocking conflicts", result.stderr)
        self.assertIn("recoverable receipts", result.stderr)

    def test_verifier_fails_closed_when_local_release_proof_points_at_wrong_frontier(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-release-frontier-") as temp_dir:
            temp_root = Path(temp_dir)
            release_proof_path = temp_root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            source_release_proof_path = REPO_ROOT / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            payload = json.loads(source_release_proof_path.read_text(encoding="utf-8"))
            payload["successor_queue_package"]["frontier_id"] = 1
            release_proof_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_LOCAL_RELEASE_PROOF"] = str(release_proof_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("successor_queue_package.frontier_id must be 4623636482", result.stderr)

    def test_verifier_fails_closed_when_local_release_proof_package_loses_closed_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-restore-release-package-") as temp_dir:
            temp_root = Path(temp_dir)
            release_proof_path = temp_root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            source_release_proof_path = REPO_ROOT / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            payload = json.loads(source_release_proof_path.read_text(encoding="utf-8"))
            payload["successor_queue_package"].pop("landed_commit", None)
            for package in payload["successor_queue_packages"]:
                if package.get("package_id") == "next90-m105-hub-workspace-continuity":
                    package.pop("status", None)
                    package["allowed_paths"] = ["Chummer.Run.Api", "scripts"]
            release_proof_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_WORKSPACE_RESTORE_RECEIPTS_LOCAL_RELEASE_PROOF"] = str(release_proof_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("successor_queue_package.landed_commit must be '4d4b3856'", result.stderr)
        self.assertIn("successor_queue_packages[next90-m105-hub-workspace-continuity].status must be 'complete'", result.stderr)
        self.assertIn("successor_queue_packages[next90-m105-hub-workspace-continuity].allowed_paths", result.stderr)


if __name__ == "__main__":
    unittest.main()
