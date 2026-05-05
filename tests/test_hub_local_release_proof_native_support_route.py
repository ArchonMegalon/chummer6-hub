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

    def test_materialized_m114_proof_includes_rule_environment_receipts(self) -> None:
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

        package = proof["successor_queue_packages_by_id"]["next90-m114-hub-rule-environment-receipts"]
        self.assertEqual(114, package["milestone_id"])
        self.assertEqual("114.3", package["work_task_id"])
        self.assertEqual("complete", package["status"])
        self.assertEqual("verify_closed_package_only", package["completion_action"])
        self.assertIn("rule-environment receipts are complete", package["do_not_reopen_reason"])

        receipts = {
            receipt.get("receipt_id"): receipt
            for receipt in proof["proof_receipts"]
            if receipt.get("package_id") == "next90-m114-hub-rule-environment-receipts"
        }
        self.assertIn("campaign_rule_environment_receipts", receipts)
        self.assertIn("support_rule_environment_receipts", receipts)
        self.assertIn("install_aware_support_receipts", receipts)
        self.assertIn("/api/v1/campaign-spine/me/rules/{entryId}", receipts["campaign_rule_environment_receipts"]["routes"])
        self.assertIn("/api/v1/support/cases/assistant", receipts["support_rule_environment_receipts"]["routes"])
        self.assertIn("/account/access", receipts["install_aware_support_receipts"]["routes"])

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

    def test_materialized_m117_proof_includes_artifact_shelf_receipts(self) -> None:
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

        package = proof["successor_queue_packages_by_id"]["next90-m117-hub-artifact-shelf-v2"]
        self.assertEqual(117, package["milestone_id"])
        self.assertEqual("117.1", package["work_task_id"])
        self.assertEqual("in_progress", package["status"])
        self.assertEqual(["artifact_shelf:v2", "artifact_audience_filters"], package["owned_surfaces"])

        receipts = {
            receipt.get("receipt_id"): receipt
            for receipt in proof["proof_receipts"]
            if receipt.get("package_id") == "next90-m117-hub-artifact-shelf-v2"
        }
        self.assertIn("artifact_shelf:v2", receipts)
        self.assertIn("artifact_audience_filters", receipts)
        self.assertIn("/artifacts", receipts["artifact_shelf:v2"]["routes"])
        self.assertIn("/artifacts/publications/{publicationId}", receipts["artifact_shelf:v2"]["routes"])
        self.assertIn("public_creator_discovery", receipts["artifact_shelf:v2"]["surfaces"])
        self.assertIn("creator_publication_detail", receipts["artifact_shelf:v2"]["surfaces"])
        self.assertTrue(
            any("manifest-authority-backed" in evidence for evidence in receipts["artifact_shelf:v2"]["evidence"]),
            "artifact shelf proof should retain manifest-authority evidence for public creator discovery.",
        )
        self.assertIn("artifact_view:personal", receipts["artifact_audience_filters"]["surfaces"])
        self.assertIn("artifact_view:campaign", receipts["artifact_audience_filters"]["surfaces"])
        self.assertIn("artifact_view:creator", receipts["artifact_audience_filters"]["surfaces"])
        self.assertIn("artifact_view:public", receipts["artifact_audience_filters"]["surfaces"])

    def test_materialized_m119_proof_includes_first_session_onboarding_receipts(self) -> None:
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

        package = proof["successor_queue_packages_by_id"]["next90-m119-hub-first-session-onboarding"]
        self.assertEqual("119.1", package["work_task_id"])
        self.assertEqual(119, package["milestone_id"])
        self.assertEqual(1130567614, package["frontier_id"])
        self.assertEqual("in_progress", package["status"])
        self.assertEqual(["first_playable_session:onboarding", "starter_lane:hub"], package["owned_surfaces"])

        receipts = {
            receipt.get("receipt_id"): receipt
            for receipt in proof["proof_receipts"]
            if receipt.get("package_id") == "next90-m119-hub-first-session-onboarding"
        }
        self.assertIn("first_playable_session:onboarding", receipts)
        self.assertIn("starter_lane:hub", receipts)
        self.assertIn("/api/v1/campaign-spine/me/workspaces/starter", receipts["first_playable_session:onboarding"]["routes"])
        self.assertIn("/home/work", receipts["first_playable_session:onboarding"]["routes"])
        self.assertIn("campaign_onboarding", receipts["first_playable_session:onboarding"]["surfaces"])
        self.assertIn("/home/work", receipts["starter_lane:hub"]["routes"])
        self.assertIn("/account/work", receipts["starter_lane:hub"]["routes"])
        self.assertIn("/contact", receipts["starter_lane:hub"]["routes"])
        self.assertIn("starter_build:follow_through", receipts["starter_lane:hub"]["surfaces"])


if __name__ == "__main__":
    unittest.main()
