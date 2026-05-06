from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m118_hub_organizer_ops.py"
MATERIALIZER = REPO_ROOT / "scripts" / "materialize_hub_local_release_proof.py"
PACKAGE_ID = "next90-m118-hub-organizer-ops"
FRONTIER_ID = 3207603971
DO_NOT_REOPEN_REASON = (
    "M118 chummer6-hub organizer, league, convention, and season contracts are complete; future shards must verify "
    "the organizer operations release-proof receipts, canonical registry row, Fleet queue row, and design queue row "
    "instead of reopening this governed community-operations slice."
)
SOURCE_FILES = [
    "Chummer.Run.Api/Contracts/OrganizerOpsContracts.cs",
    "Chummer.Campaign.Contracts/CampaignContracts.cs",
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs",
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
    "Chummer.Run.Api/Views/Accounts/Account.cshtml",
    "Chummer.Run.Api/Views/PublicLanding/Home.cshtml",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/materialize_hub_local_release_proof.py",
    "scripts/ai/verify.sh",
    "scripts/verify_next90_m118_hub_organizer_ops.py",
    "tests/test_next90_m118_hub_organizer_ops.py",
]


class Next90M118HubOrganizerOpsTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_organizer_ops(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m118-accepts-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            verifier_paths = self.prepare_verifier_inputs(temp_root)
            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m118 hub organizer ops proof passed", result.stdout)

    def test_verify_script_runs_m118_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/verify_next90_m118_hub_organizer_ops.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m118_hub_organizer_ops.py", verify_script)

    def test_verifier_fails_when_queue_row_reopens(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m118-queue-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            verifier_paths = self.prepare_verifier_inputs(temp_root)
            queue_path = temp_root / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            payload = self.build_queue_payload()
            payload["items"][0]["status"] = "in_progress"
            payload["items"][0].pop("completion_action", None)
            payload["items"][0].pop("do_not_reopen_reason", None)
            payload["items"][0].pop("proof", None)
            queue_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(
                temp_root,
                queue_path=queue_path,
                design_queue_path=verifier_paths["design_queue_path"],
                successor_registry_path=verifier_paths["successor_registry_path"],
                local_release_proof_path=verifier_paths["local_release_proof_path"],
                served_release_proof_path=verifier_paths["served_release_proof_path"],
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status must be 'complete'", result.stderr)

    def test_verifier_fails_when_design_queue_row_drifts_from_fleet_queue(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m118-queue-parity-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            verifier_paths = self.prepare_verifier_inputs(temp_root)
            design_queue_path = temp_root / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            payload = self.build_queue_payload()
            payload["items"][0]["owned_surfaces"] = ["organizer_ops"]
            design_queue_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(
                temp_root,
                queue_path=verifier_paths["queue_path"],
                design_queue_path=design_queue_path,
                successor_registry_path=verifier_paths["successor_registry_path"],
                local_release_proof_path=verifier_paths["local_release_proof_path"],
                served_release_proof_path=verifier_paths["served_release_proof_path"],
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fleet and design queue rows for next90-m118-hub-organizer-ops must match exactly", result.stderr)

    def test_verifier_fails_when_registry_work_task_lacks_complete_status(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m118-registry-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            verifier_paths = self.prepare_verifier_inputs(temp_root)
            registry_path = temp_root / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            payload = self.build_registry_payload()
            payload["milestones"][0]["work_tasks"][0].pop("status", None)
            registry_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(
                temp_root,
                queue_path=verifier_paths["queue_path"],
                design_queue_path=verifier_paths["design_queue_path"],
                successor_registry_path=registry_path,
                local_release_proof_path=verifier_paths["local_release_proof_path"],
                served_release_proof_path=verifier_paths["served_release_proof_path"],
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("work task 118.1 status must be 'complete'", result.stderr)

    def test_verifier_fails_when_release_proof_loses_organizer_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m118-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            verifier_paths = self.prepare_verifier_inputs(temp_root)
            proof_path = verifier_paths["local_release_proof_path"]
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof["proof_receipts"] = [
                receipt
                for receipt in proof["proof_receipts"]
                if not (receipt.get("package_id") == PACKAGE_ID and receipt.get("receipt_id") == "organizer_ops")
            ]
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
            verifier_paths["served_release_proof_path"].write_text(proof_path.read_text(encoding="utf-8"), encoding="utf-8")

            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected exactly one next90-m118-hub-organizer-ops receipt 'organizer_ops'", result.stderr)

    def test_materialized_release_proof_includes_m118_organizer_receipts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m118-proof-materialize-") as temp_dir:
            proof_path = Path(temp_dir) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
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

        package = proof["successor_queue_packages_by_id"][PACKAGE_ID]
        self.assertEqual(118, package["milestone_id"])
        self.assertEqual("118.1", package["work_task_id"])
        self.assertEqual("complete", package["status"])
        self.assertEqual(FRONTIER_ID, package["frontier_id"])
        self.assertEqual("verify_closed_package_only", package["completion_action"])
        self.assertEqual(DO_NOT_REOPEN_REASON, package["do_not_reopen_reason"])

        receipts = {
            receipt.get("receipt_id"): receipt
            for receipt in proof["proof_receipts"]
            if receipt.get("package_id") == PACKAGE_ID
        }
        self.assertIn("organizer_ops", receipts)
        self.assertIn("league_convention_season_ops", receipts)
        self.assertIn("/api/v1/campaign-spine/me/organizer-ops", receipts["organizer_ops"]["routes"])
        self.assertIn("organizer_roles", receipts["organizer_ops"]["surfaces"])
        self.assertIn("season_event_lanes", receipts["league_convention_season_ops"]["surfaces"])
        self.assertIn("support_escalation:organizer", receipts["league_convention_season_ops"]["surfaces"])

    def test_verifier_fails_when_served_release_proof_drifts_from_local_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m118-served-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            verifier_paths = self.prepare_verifier_inputs(temp_root)
            served_proof_path = verifier_paths["served_release_proof_path"]
            served_proof = json.loads(served_proof_path.read_text(encoding="utf-8"))
            served_proof["proof_receipts"] = [
                receipt
                for receipt in served_proof["proof_receipts"]
                if not (receipt.get("package_id") == PACKAGE_ID and receipt.get("receipt_id") == "league_convention_season_ops")
            ]
            served_proof_path.write_text(json.dumps(served_proof, indent=2) + "\n", encoding="utf-8")

            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("repo-local and served release proof receipt 'league_convention_season_ops'", result.stderr)

    def test_verifier_fails_when_account_view_loses_publication_summary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m118-account-view-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            account_view_path = temp_root / "Chummer.Run.Api/Views/Accounts/Account.cshtml"
            account_view_text = account_view_path.read_text(encoding="utf-8")
            account_view_path.write_text(
                account_view_text.replace("@op.ArtifactPublicationSummary", "@op.LeagueOperationsSummary", 1),
                encoding="utf-8",
            )

            verifier_paths = self.prepare_verifier_inputs(temp_root)
            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("@op.ArtifactPublicationSummary", result.stderr)

    def test_verifier_fails_when_home_view_loses_support_summary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m118-home-view-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            home_view_path = temp_root / "Chummer.Run.Api/Views/PublicLanding/Home.cshtml"
            home_view_text = home_view_path.read_text(encoding="utf-8")
            home_view_path.write_text(
                home_view_text.replace("@leadCommunityOperation.SupportEscalationSummary", "@leadCommunityOperation.OperationsSummary"),
                encoding="utf-8",
            )

            verifier_paths = self.prepare_verifier_inputs(temp_root)
            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("@leadCommunityOperation.SupportEscalationSummary", result.stderr)

    def test_verifier_fails_when_controller_loses_organizer_endpoint(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m118-controller-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/CampaignSpineController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace("GetMyOrganizerOperations", "GetMyCommunityOrganizerOperations", 1),
                encoding="utf-8",
            )

            verifier_paths = self.prepare_verifier_inputs(temp_root)
            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GetMyOrganizerOperations", result.stderr)

    def copy_sources(self, temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def prepare_verifier_inputs(self, temp_root: Path) -> dict[str, Path]:
        queue_path = temp_root / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
        queue_path.write_text(yaml.safe_dump(self.build_queue_payload(), sort_keys=False), encoding="utf-8")

        design_queue_path = temp_root / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
        design_queue_path.write_text(yaml.safe_dump(self.build_queue_payload(), sort_keys=False), encoding="utf-8")

        registry_path = temp_root / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
        registry_path.write_text(yaml.safe_dump(self.build_registry_payload(), sort_keys=False), encoding="utf-8")

        local_proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
        served_proof_path = temp_root / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
        local_proof_path.parent.mkdir(parents=True, exist_ok=True)
        served_proof_path.parent.mkdir(parents=True, exist_ok=True)
        self.materialize_proof(local_proof_path)
        served_proof_path.write_text(local_proof_path.read_text(encoding="utf-8"), encoding="utf-8")

        return {
            "queue_path": queue_path,
            "design_queue_path": design_queue_path,
            "successor_registry_path": registry_path,
            "local_release_proof_path": local_proof_path,
            "served_release_proof_path": served_proof_path,
        }

    @staticmethod
    def materialize_proof(output_path: Path) -> None:
        result = subprocess.run(
            [
                "python3",
                str(MATERIALIZER),
                str(output_path),
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
        if result.returncode != 0:
            raise AssertionError(f"materializer failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")

    @staticmethod
    def build_queue_payload() -> dict:
        return {
            "items": [
                {
                    "title": "Land organizer, league, convention, and season contracts",
                    "task": "Add roles, rosters, events, permissions, artifact publication, and support escalation contracts for community-scale operations.",
                    "package_id": PACKAGE_ID,
                    "work_task_id": 118.1,
                    "milestone_id": 118,
                    "status": "complete",
                    "wave": "W13",
                    "repo": "chummer6-hub",
                    "completion_action": "verify_closed_package_only",
                    "do_not_reopen_reason": DO_NOT_REOPEN_REASON,
                    "proof": [
                        "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Contracts/OrganizerOpsContracts.cs",
                        "/docker/chummercomplete/chummer6-hub/Chummer.Campaign.Contracts/CampaignContracts.cs",
                        "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/CampaignSpineController.cs",
                        "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
                        "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/Accounts/Account.cshtml",
                        "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Home.cshtml",
                        "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs",
                        "/docker/chummercomplete/chummer6-hub/scripts/materialize_hub_local_release_proof.py",
                        "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m118_hub_organizer_ops.py",
                        "/docker/chummercomplete/chummer6-hub/tests/test_next90_m118_hub_organizer_ops.py",
                        "/docker/chummercomplete/chummer6-hub/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
                        "python3 scripts/verify_next90_m118_hub_organizer_ops.py",
                        "python3 -m unittest tests/test_next90_m118_hub_organizer_ops.py",
                        "bash scripts/ai/verify.sh",
                    ],
                    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
                    "owned_surfaces": ["organizer_ops", "league_convention_season_ops"],
                }
            ]
        }

    @staticmethod
    def build_registry_payload() -> dict:
        return {
            "milestones": [
                {
                    "id": 118,
                    "title": "Organizer, league, convention, and season operations",
                    "status": "in_progress",
                    "dependencies": [112, 113, 116, 117],
                    "exit_criteria": [
                        "Organizer, league, convention, and season workflows can manage groups, rosters, events, permissions, artifact publication, and support escalation from one governed operations lane.",
                        "Community operations remain auditable and bounded instead of becoming operator-only spreadsheets.",
                        "Fleet and EA can compile operator packets and followthrough from the same governed state.",
                    ],
                    "work_tasks": [
                        {
                            "id": "118.1",
                            "owner": "chummer6-hub",
                            "title": "Land organizer, league, convention, and season operation contracts with roles, rosters, events, and audit receipts.",
                            "status": "complete",
                            "evidence": [
                                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Contracts/OrganizerOpsContracts.cs and /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/CampaignSpineController.cs now publish one governed organizer-operations dashboard contract and API route for organizer, league, convention, and season work.",
                                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignSpineService.cs now composes organizer roles, permissions, roster movement, season lanes, artifact publication posture, and support-escalation posture from the shared campaign/community truth instead of separate operator notes.",
                                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/Accounts/Account.cshtml and /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Home.cshtml now keep organizer publication and support posture visible on the signed-in work rails without splitting it away from the governed operations card.",
                                "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs proves organizer role assignments, permissions, roster movement, season lanes, artifact publication posture, and tracked support escalation survive the shared hub API and signed-in surfaces.",
                                "/docker/chummercomplete/chummer6-hub/scripts/materialize_hub_local_release_proof.py, /docker/chummercomplete/chummer6-hub/scripts/verify_next90_m118_hub_organizer_ops.py, and /docker/chummercomplete/chummer6-hub/tests/test_next90_m118_hub_organizer_ops.py keep the closed-package queue, registry, and release-proof receipts executable inside the repo.",
                                "python3 scripts/verify_next90_m118_hub_organizer_ops.py exits 0, python3 -m unittest tests/test_next90_m118_hub_organizer_ops.py exits 0, and bash scripts/ai/verify.sh keeps the dedicated M118 verifier in the shared verify lane.",
                            ],
                        },
                        {
                            "id": "118.2",
                            "owner": "chummer6-ui",
                            "title": "Surface organizer operations on desktop without confusing GM, player, creator, and operator roles.",
                        },
                    ],
                }
            ]
        }

    def run_verifier(
        self,
        temp_root: Path,
        *,
        queue_path: Path,
        design_queue_path: Path,
        successor_registry_path: Path,
        local_release_proof_path: Path,
        served_release_proof_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_ROOT"] = str(temp_root)
        env["CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_QUEUE_STAGING"] = str(queue_path)
        env["CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_DESIGN_QUEUE_STAGING"] = str(design_queue_path)
        env["CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_SUCCESSOR_REGISTRY"] = str(successor_registry_path)
        env["CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_LOCAL_RELEASE_PROOF"] = str(local_release_proof_path)
        env["CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_SERVED_RELEASE_PROOF"] = str(served_release_proof_path)
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_next90_m118_hub_organizer_ops.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
