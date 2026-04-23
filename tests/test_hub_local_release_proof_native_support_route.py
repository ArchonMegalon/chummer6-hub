from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = REPO_ROOT / "scripts" / "materialize_hub_local_release_proof.py"
NATIVE_SUPPORT_ROUTE = "/api/v1/install-linking/continuation/support"


class HubLocalReleaseProofNativeSupportRouteTests(unittest.TestCase):
    def test_materialized_m102_proof_includes_native_support_route(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            result = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
            proof = json.loads(proof_path.read_text(encoding="utf-8"))

        support_receipts = [
            receipt
            for receipt in proof["proof_receipts"]
            if receipt.get("receipt_id") == "support_followthrough:install_truth"
        ]
        self.assertEqual(1, len(support_receipts))
        self.assertIn(NATIVE_SUPPORT_ROUTE, support_receipts[0]["routes"])

    def test_materialized_m111_proof_includes_support_and_release_concierge_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            result = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
            proof = json.loads(proof_path.read_text(encoding="utf-8"))

        package = proof["successor_queue_packages_by_id"]["next90-m111-hub-support-concierge"]
        self.assertEqual(111, package["milestone_id"])
        self.assertEqual("complete", package["status"])
        self.assertEqual("verify_closed_package_only", package["completion_action"])
        self.assertEqual("3fb14923", package["landed_commit"])
        self.assertIn("future shards must verify", package["do_not_reopen_reason"])
        self.assertEqual(["install_aware_support_concierge", "release_concierge:hub"], package["owned_surfaces"])

        receipts = {
            receipt.get("receipt_id"): receipt
            for receipt in proof["proof_receipts"]
            if receipt.get("package_id") == "next90-m111-hub-support-concierge"
        }
        self.assertIn("install_aware_support_concierge", receipts)
        self.assertIn("release_concierge:hub", receipts)
        self.assertIn("/api/v1/support/cases/{caseId}/concierge", receipts["install_aware_support_concierge"]["routes"])
        self.assertIn("/help", receipts["release_concierge:hub"]["routes"])
        self.assertIn("/now", receipts["release_concierge:hub"]["routes"])
        self.assertIn("/status", receipts["release_concierge:hub"]["routes"])
        self.assertIn("/downloads/install/{artifactId}", receipts["release_concierge:hub"]["routes"])

    def test_materialized_m108_proof_includes_campaign_and_mission_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            result = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
            proof = json.loads(proof_path.read_text(encoding="utf-8"))

        package = proof["successor_queue_packages_by_id"]["next90-m108-hub-campaign-briefing-bundles"]
        self.assertEqual(108, package["milestone_id"])
        self.assertEqual("complete", package["status"])
        self.assertEqual("verify_closed_package_only", package["completion_action"])
        self.assertEqual("d0a84683", package["landed_commit"])
        self.assertEqual(["campaign_cold_open_pack", "mission_briefing_reel"], package["owned_surfaces"])

        receipts = {
            receipt.get("receipt_id"): receipt
            for receipt in proof["proof_receipts"]
            if receipt.get("package_id") == "next90-m108-hub-campaign-briefing-bundles"
        }
        self.assertIn("campaign_cold_open_pack", receipts)
        self.assertIn("mission_briefing_reel", receipts)
        self.assertIn("/artifacts/campaigns/{campaignId}/cold-open", receipts["campaign_cold_open_pack"]["routes"])
        self.assertIn("/artifacts/missions/{missionId}/briefing", receipts["mission_briefing_reel"]["routes"])

    def test_materialized_m110_proof_includes_runsite_orientation_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            result = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
            proof = json.loads(proof_path.read_text(encoding="utf-8"))

        package = proof["successor_queue_packages_by_id"]["next90-m110-hub-runsite-orientation-requests"]
        self.assertEqual(110, package["milestone_id"])
        self.assertEqual(1545739925, package["frontier_id"])
        self.assertEqual("complete", package["status"])
        self.assertEqual("verify_closed_package_only", package["completion_action"])
        self.assertEqual(["runsite_orientation_requests", "route_summary:artifact_launch"], package["owned_surfaces"])

        receipts = {
            receipt.get("receipt_id"): receipt
            for receipt in proof["proof_receipts"]
            if receipt.get("package_id") == "next90-m110-hub-runsite-orientation-requests"
        }
        self.assertIn("runsite_orientation_requests", receipts)
        self.assertIn("route_summary:artifact_launch", receipts)
        self.assertIn("/api/internal/runsite-orientation/requests", receipts["runsite_orientation_requests"]["routes"])
        self.assertIn("preview_safe_truth:pre_session", receipts["runsite_orientation_requests"]["surfaces"])
        self.assertIn("/artifacts/routes/{routeSummaryId}/{routeSegmentId}", receipts["route_summary:artifact_launch"]["routes"])
        self.assertIn("route_preview:inspectable_truth", receipts["route_summary:artifact_launch"]["surfaces"])


if __name__ == "__main__":
    unittest.main()
