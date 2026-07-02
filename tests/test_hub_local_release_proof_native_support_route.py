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
    def test_materialized_proof_routes_match_release_channel_contract(self) -> None:
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

        self.assertEqual(
            [
                "/downloads/install/avalonia-linux-x64-installer",
                "/home/access",
                "/home/work",
                "/account/access",
                "/account/work",
                "/account/support",
                "/contact",
                "/downloads",
                "/downloads/install/avalonia-osx-arm64-installer",
                "/downloads/install/avalonia-win-x64-installer",
            ],
            proof["proof_routes"],
        )
        receipts = {receipt.get("receipt_id"): receipt for receipt in proof["proof_receipts"]}
        self.assertIn(
            "/account/work#campaign-consequences",
            receipts["campaign_memory:consequence_truth"]["routes"],
        )
        self.assertIn(
            "/account/work#aftermath-packages",
            receipts["downtime_aftermath:api"]["routes"],
        )

    def test_materialized_m141_proof_includes_direct_import_route_receipts(self) -> None:
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

        receipts = {receipt.get("receipt_id"): receipt for receipt in proof["proof_receipts"]}
        self.assertIn("menu:translator", receipts)
        self.assertIn("menu:xml_editor", receipts)
        self.assertIn("menu:hero_lab_importer", receipts)
        self.assertIn("workflow:import_oracle", receipts)
        self.assertEqual(
            "next90-m141-ui-capture-direct-screenshot-and-runtime-proof-for-translator-xml-amendment",
            receipts["menu:translator"]["package_id"],
        )
        self.assertIn("source:translator_route", receipts["menu:translator"]["routes"])
        self.assertIn("source:xml_amendment_editor_route", receipts["menu:xml_editor"]["routes"])
        self.assertIn("source:hero_lab_importer_route", receipts["menu:hero_lab_importer"]["routes"])
        self.assertIn("family:legacy_and_adjacent_import_oracles", receipts["workflow:import_oracle"]["routes"])

    def test_materialized_m102_proof_includes_desktop_client_readiness_snapshot_and_bounded_routes_receipt(self) -> None:
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

        readiness = proof.get("desktop_client_readiness")
        self.assertIsInstance(readiness, dict)
        self.assertIn(readiness.get("status"), {"pass", "fail", "unknown"})
        self.assertEqual(
            readiness.get("desktop_client_missing"),
            "desktop_client" in set(readiness.get("missing_coverage_keys", [])),
        )
        self.assertTrue(str(readiness.get("reason") or "").strip())

        receipts = {
            receipt.get("receipt_id"): receipt
            for receipt in proof["proof_receipts"]
            if receipt.get("package_id") == "next90-m102-hub-desktop-native-trust"
        }
        self.assertIn("desktop_client_readiness:bounded_routes", receipts)
        self.assertIn("/downloads", receipts["desktop_client_readiness:bounded_routes"]["routes"])
        self.assertIn("/status", receipts["desktop_client_readiness:bounded_routes"]["routes"])
        self.assertIn("/artifacts", receipts["desktop_client_readiness:bounded_routes"]["routes"])
        self.assertIn("/artifacts/publications/{publicationId}", receipts["desktop_client_readiness:bounded_routes"]["routes"])
        self.assertIn(
            "desktop_client_readiness:bounded_routes",
            receipts["desktop_client_readiness:bounded_routes"]["surfaces"],
        )
        self.assertIn(
            "public_proof_shelf:release_bundles",
            receipts["desktop_client_readiness:bounded_routes"]["surfaces"],
        )

    def test_materialized_release_bundle_receipt_covers_public_windows_and_linux_installers(self) -> None:
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

        receipts = {receipt.get("receipt_id"): receipt for receipt in proof["proof_receipts"]}
        release_bundle_receipt = receipts["public_proof_shelf:release_bundles"]
        self.assertIn("/downloads/install/avalonia-linux-x64-installer", release_bundle_receipt["routes"])
        self.assertIn("/artifacts/release-bundles/avalonia-linux-x64-installer", release_bundle_receipt["routes"])
        self.assertIn("/artifacts/release-bundles/avalonia-linux-x64-installer/preview_card", release_bundle_receipt["routes"])
        self.assertIn("/downloads/install/avalonia-win-x64-installer", release_bundle_receipt["routes"])
        self.assertIn("/artifacts/release-bundles/avalonia-win-x64-installer", release_bundle_receipt["routes"])
        self.assertIn("/artifacts/release-bundles/avalonia-win-x64-installer/preview_card", release_bundle_receipt["routes"])

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
        self.assertEqual("complete", package["status"])
        self.assertEqual("verify_closed_package_only", package["completion_action"])
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
        self.assertIn("creator, or public", receipts["artifact_audience_filters"]["summary"])

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
        self.assertEqual("complete", package["status"])
        self.assertEqual("TO_BE_FILLED_M119_COMMIT", package["landed_commit"])
        self.assertEqual("verify_closed_package_only", package["completion_action"])
        self.assertEqual(["first_playable_session:onboarding", "starter_lane:hub"], package["owned_surfaces"])
        self.assertIn("guided first-playable-session onboarding is complete", package["do_not_reopen_reason"])
        self.assertIn("python3 scripts/verify_next90_m119_hub_first_session_onboarding.py", package["proof"])

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

    def test_materialized_m120_proof_includes_public_launch_health_receipts(self) -> None:
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

        package = proof["successor_queue_packages_by_id"]["next90-m120-hub-public-launch-health"]
        self.assertEqual("120.1", package["work_task_id"])
        self.assertEqual(120, package["milestone_id"])
        self.assertEqual(4442751895, package["frontier_id"])
        self.assertEqual("complete", package["status"])
        self.assertEqual("verify_closed_package_only", package["completion_action"])
        self.assertEqual("TO_BE_FILLED_M120_COMMIT", package["landed_commit"])
        self.assertIn("public trust and launch-health publication package is complete", package["do_not_reopen_reason"])
        self.assertEqual(
            "Publish public trust, status, release, and proof-shelf surfaces from registry and governor truth.",
            package["title"],
        )
        self.assertEqual(["public_trust_surface:v3", "launch_health:public"], package["owned_surfaces"])

        public_trust_surface = proof["publicTrustSurface"]
        self.assertEqual("/status", public_trust_surface["statusRoute"])
        self.assertEqual("/api/public/weekly-pulse", public_trust_surface["weeklyPulseRoute"])
        self.assertEqual("/api/public/progress-poster.svg", public_trust_surface["progressPosterRoute"])
        self.assertEqual(
            ["Live", "Preview", "Fallback", "Revoked", "Fixed", "Blocked", "Proof recency", "Support pulse", "Adoption health"],
            public_trust_surface["launchHealthLabels"],
        )

        receipts = {
            receipt.get("receipt_id"): receipt
            for receipt in proof["proof_receipts"]
            if receipt.get("package_id") == "next90-m120-hub-public-launch-health"
        }
        self.assertIn("public_trust_surface:v3", receipts)
        self.assertIn("launch_health:public", receipts)

    def test_materialized_m141_proof_includes_import_route_review_required_receipt(self) -> None:
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

        package = proof["successor_queue_packages_by_id"][
            "next90-m141-hub-keep-route-support-and-publication-surfaces-from-claiming-parity-for-the"
        ]
        self.assertEqual("141.3", package["work_task_id"])
        self.assertEqual(141, package["milestone_id"])
        self.assertEqual(4062147200, package["frontier_id"])
        self.assertEqual("complete", package["status"])
        self.assertEqual("verify_closed_package_only", package["completion_action"])
        self.assertEqual(
            ["keep_route_support_and_publication_surfaces_from_claimin:hub"],
            package["owned_surfaces"],
        )
        self.assertIn("import-route review-required guard is complete", package["do_not_reopen_reason"])

        receipts = {
            receipt.get("receipt_id"): receipt
            for receipt in proof["proof_receipts"]
            if receipt.get("package_id")
            == "next90-m141-hub-keep-route-support-and-publication-surfaces-from-claiming-parity-for-the"
        }
        self.assertIn("keep_route_support_and_publication_surfaces_from_claimin:hub", receipts)
        self.assertIn("/downloads", receipts["keep_route_support_and_publication_surfaces_from_claimin:hub"]["routes"])
        self.assertIn("/status", receipts["keep_route_support_and_publication_surfaces_from_claimin:hub"]["routes"])
        self.assertIn(
            "/artifacts/publications/{publicationId}",
            receipts["keep_route_support_and_publication_surfaces_from_claimin:hub"]["routes"],
        )
        self.assertIn(
            "artifact_shelf:v2",
            receipts["keep_route_support_and_publication_surfaces_from_claimin:hub"]["surfaces"],
        )

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
        self.assertEqual("complete", package["status"])
        self.assertEqual("TO_BE_FILLED_M119_COMMIT", package["landed_commit"])
        self.assertEqual("verify_closed_package_only", package["completion_action"])
        self.assertEqual(["first_playable_session:onboarding", "starter_lane:hub"], package["owned_surfaces"])
        self.assertIn("guided first-playable-session onboarding is complete", package["do_not_reopen_reason"])
        self.assertIn("python3 scripts/verify_next90_m119_hub_first_session_onboarding.py", package["proof"])

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
