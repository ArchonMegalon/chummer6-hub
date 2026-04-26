from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_campaign_consequence_truth.py"
RELEASE_PROOF = REPO_ROOT / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
SOURCE_FILES = [
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs",
    "Chummer.Run.Api/Contracts/CampaignWorkspaceServerPlaneContracts.cs",
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
    "tests/RunServicesVerification/CampaignSpineRestoreVerification.cs",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/materialize_campaign_os_local_proof.py",
    "scripts/verify_campaign_consequence_truth.py",
    "scripts/ai/verify.sh",
    "tests/test_campaign_consequence_truth.py",
]


class CampaignConsequenceTruthProofTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_campaign_consequence_truth(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("campaign consequence truth proof passed", result.stdout)

    def test_standard_verify_runs_campaign_consequence_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")

        self.assertIn("python3 scripts/verify_campaign_consequence_truth.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_campaign_consequence_truth.py", verify_script)

    def test_verifier_fails_when_service_drops_governed_aftermath_source_kind(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-source-kind-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            service_path = temp_root / "Chummer.Run.Api/Services/Community/CampaignSpineService.cs"
            service_text = service_path.read_text(encoding="utf-8")
            service_path.write_text(
                service_text.replace(
                    'private const string GovernedAftermathPackageSourceKind = "governed_aftermath_package";',
                    'private const string GovernedAftermathPackageSourceKind = "aftermath_package";',
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GovernedAftermathPackageSourceKind", result.stderr)

    def test_verifier_fails_when_queue_owned_surfaces_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-queue-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            queue_path.write_text(
                """
items:
  - title: Promote campaign consequence state into governed campaign APIs
    task: Land downtime, aftermath, heat, faction, contact, and reputation state with receipts and return-loop actions.
    package_id: next90-m112-hub-campaign-consequence-truth
    frontier_id: 4730880976
    milestone_id: 112
    wave: W11
    repo: chummer6-hub
    allowed_paths:
      - Chummer.Run.Api
      - scripts
      - tests
    owned_surfaces:
      - campaign_memory:consequence_truth
      - stale_surface
""".strip()
                + "\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_QUEUE_STAGING"] = str(queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("owned_surfaces must be", result.stderr)

    def test_verifier_fails_when_queue_frontier_id_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-queue-frontier-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            queue_path.write_text(
                """
items:
  - title: Promote campaign consequence state into governed campaign APIs
    task: Land downtime, aftermath, heat, faction, contact, and reputation state with receipts and return-loop actions.
    package_id: next90-m112-hub-campaign-consequence-truth
    work_task_id: 112.1
    milestone_id: 112
    wave: W11
    repo: chummer6-hub
    allowed_paths:
      - Chummer.Run.Api
      - scripts
      - tests
    owned_surfaces:
      - campaign_memory:consequence_truth
      - downtime_aftermath:api
""".strip()
                + "\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_QUEUE_STAGING"] = str(queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("frontier_id must be 4730880976", result.stderr)

    def test_verifier_fails_when_queue_work_task_id_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-queue-task-id-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            queue_path.write_text(
                """
items:
  - title: Promote campaign consequence state into governed campaign APIs
    task: Land downtime, aftermath, heat, faction, contact, and reputation state with receipts and return-loop actions.
    package_id: next90-m112-hub-campaign-consequence-truth
    frontier_id: 4730880976
    work_task_id: 112.9
    milestone_id: 112
    wave: W11
    repo: chummer6-hub
    allowed_paths:
      - Chummer.Run.Api
      - scripts
      - tests
    owned_surfaces:
      - campaign_memory:consequence_truth
      - downtime_aftermath:api
""".strip()
                + "\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_QUEUE_STAGING"] = str(queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("work_task_id must be 112.1", result.stderr)

    def test_verifier_fails_when_fleet_and_design_queue_closure_metadata_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-queue-parity-") as temp_dir:
            fleet_queue_path = Path(temp_dir) / "fleet-queue.yaml"
            design_queue_path = Path(temp_dir) / "design-queue.yaml"
            queue_template = """
items:
  - title: Promote campaign consequence state into governed campaign APIs
    task: Land downtime, aftermath, heat, faction, contact, and reputation state with receipts and return-loop actions.
    package_id: next90-m112-hub-campaign-consequence-truth
    frontier_id: 4730880976
    work_task_id: 112.1
    milestone_id: 112
    wave: W11
    repo: chummer6-hub
    allowed_paths:
      - Chummer.Run.Api
      - scripts
      - tests
    owned_surfaces:
      - campaign_memory:consequence_truth
      - downtime_aftermath:api
""".strip()
            fleet_queue_path.write_text(
                queue_template
                + """
    status: complete
    landed_commit: abc1234
""",
                encoding="utf-8",
            )
            design_queue_path.write_text(queue_template + "\n", encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_QUEUE_STAGING"] = str(fleet_queue_path)
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_DESIGN_QUEUE_STAGING"] = str(design_queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Fleet queue and design queue package rows drifted", result.stderr)

    def test_verifier_fails_when_registry_closes_without_queue_closure_parity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-registry-complete-") as temp_dir:
            registry_path = Path(temp_dir) / "registry.yaml"
            registry_path.write_text(
                """
milestones:
  - id: 112
    title: Campaign memory, downtime, heat, faction, and contact truth
    work_tasks:
      - id: 112.1
        owner: chummer6-hub
        title: Promote downtime, aftermath, heat, faction, contact, and reputation state into governed campaign APIs and receipts.
        status: complete
        landed_commit: abc1234
""".strip()
                + "\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_SUCCESSOR_REGISTRY"] = str(registry_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("successor registry completion_action must be 'verify_closed_package_only'", result.stderr)

    def test_verifier_fails_when_completed_queue_row_drops_do_not_reopen_reason(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-closeout-reason-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            queue_path.write_text(
                """
items:
  - title: Promote campaign consequence state into governed campaign APIs
    task: Land downtime, aftermath, heat, faction, contact, and reputation state with receipts and return-loop actions.
    package_id: next90-m112-hub-campaign-consequence-truth
    frontier_id: 4730880976
    work_task_id: 112.1
    milestone_id: 112
    status: complete
    wave: W11
    repo: chummer6-hub
    completion_action: verify_closed_package_only
    landed_commit: f2b0b5a6
    allowed_paths:
      - Chummer.Run.Api
      - scripts
      - tests
    owned_surfaces:
      - campaign_memory:consequence_truth
      - downtime_aftermath:api
""".strip()
                + "\n",
                encoding="utf-8",
            )
            registry_path = Path(temp_dir) / "registry.yaml"
            registry_path.write_text(
                """
milestones:
  - id: 112
    title: Campaign memory, downtime, heat, faction, and contact truth
    work_tasks:
      - id: 112.1
        owner: chummer6-hub
        title: Promote downtime, aftermath, heat, faction, contact, and reputation state into governed campaign APIs and receipts.
        status: complete
        completion_action: verify_closed_package_only
        do_not_reopen_reason: M112 chummer6-hub campaign consequence truth is complete; future shards must verify the governed campaign consequence proof, local release proof receipts, registry row, queue row, and design queue row instead of reopening this package.
        landed_commit: f2b0b5a6
""".strip()
                + "\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_QUEUE_STAGING"] = str(queue_path)
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_DESIGN_QUEUE_STAGING"] = str(queue_path)
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_SUCCESSOR_REGISTRY"] = str(registry_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("do_not_reopen_reason must match", result.stderr)

    def test_verifier_fails_when_release_proof_drops_m112_package_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-release-proof-") as temp_dir:
            proof_path = Path(temp_dir) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            payload = json.loads(RELEASE_PROOF.read_text(encoding="utf-8"))
            payload["successor_queue_packages_by_id"].pop("next90-m112-hub-campaign-consequence-truth", None)
            payload["successor_queue_packages"] = [
                package
                for package in payload["successor_queue_packages"]
                if package.get("package_id") != "next90-m112-hub-campaign-consequence-truth"
            ]
            payload["proof_receipts"] = [
                receipt
                for receipt in payload["proof_receipts"]
                if receipt.get("package_id") != "next90-m112-hub-campaign-consequence-truth"
            ]
            proof_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            fleet_queue_path = Path(temp_dir) / "fleet-queue.yaml"
            design_queue_path = Path(temp_dir) / "design-queue.yaml"
            registry_path = Path(temp_dir) / "registry.yaml"
            complete_queue = """
items:
  - title: Promote campaign consequence state into governed campaign APIs
    task: Land downtime, aftermath, heat, faction, contact, and reputation state with receipts and return-loop actions.
    package_id: next90-m112-hub-campaign-consequence-truth
    frontier_id: 4730880976
    work_task_id: 112.1
    milestone_id: 112
    status: complete
    wave: W11
    repo: chummer6-hub
    completion_action: verify_closed_package_only
    do_not_reopen_reason: M112 chummer6-hub campaign consequence truth is complete; future shards must verify the governed campaign consequence proof, local release proof receipts, registry row, queue row, and design queue row instead of reopening this package.
    landed_commit: f2b0b5a6
    allowed_paths:
      - Chummer.Run.Api
      - scripts
      - tests
    owned_surfaces:
      - campaign_memory:consequence_truth
      - downtime_aftermath:api
""".strip()
            fleet_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                """
milestones:
  - id: 112
    title: Campaign memory, downtime, heat, faction, and contact truth
    work_tasks:
      - id: 112.1
        owner: chummer6-hub
        title: Promote downtime, aftermath, heat, faction, contact, and reputation state into governed campaign APIs and receipts.
        status: complete
        completion_action: verify_closed_package_only
        do_not_reopen_reason: M112 chummer6-hub campaign consequence truth is complete; future shards must verify the governed campaign consequence proof, local release proof receipts, registry row, queue row, and design queue row instead of reopening this package.
        landed_commit: f2b0b5a6
""".strip()
                + "\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_QUEUE_STAGING"] = str(fleet_queue_path)
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_DESIGN_QUEUE_STAGING"] = str(design_queue_path)
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_SUCCESSOR_REGISTRY"] = str(registry_path)
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_RELEASE_PROOF"] = str(proof_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("successor_queue_packages_by_id must include next90-m112-hub-campaign-consequence-truth", result.stderr)

    def test_verifier_rejects_active_run_markers_in_generated_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-proof-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            payload = json.loads(
                (REPO_ROOT / ".codex-studio" / "published" / "HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json").read_text(
                    encoding="utf-8"
                )
            )
            payload["required_markers"]["campaign_session_recover_recap"].append(
                "TASK_LOCAL_TELEMETRY.generated.json is forbidden completion proof."
            )
            proof_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_PROOF"] = str(proof_path)

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

    def test_verifier_fails_when_generated_proof_drops_package_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-package-proof-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            payload = json.loads(
                (REPO_ROOT / ".codex-studio" / "published" / "HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json").read_text(
                    encoding="utf-8"
                )
            )
            payload["package_proof"] = {
                "package_id": "next90-m112-hub-campaign-consequence-truth",
                "title": "Promote campaign consequence state into governed campaign APIs",
                "task": "Land downtime, aftermath, heat, faction, contact, and reputation state with receipts and return-loop actions.",
                "milestone_id": 112,
                "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
                "owned_surfaces": ["campaign_memory:consequence_truth", "downtime_aftermath:api"],
            }
            proof_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_PROOF"] = str(proof_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("campaign os proof package_proof drifted", result.stderr)

    def test_verifier_fails_when_generated_proof_drops_heat_marker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-proof-marker-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            payload = json.loads(
                (REPO_ROOT / ".codex-studio" / "published" / "HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json").read_text(
                    encoding="utf-8"
                )
            )
            marker = (
                'consequenceUpdatePayload.Receipts.Any(item => string.Equals(item.SourceKind, "governed_consequence_update", '
                'StringComparison.Ordinal))'
            )
            payload["required_markers"]["campaign_session_recover_recap"] = [
                item for item in payload["required_markers"]["campaign_session_recover_recap"] if item != marker
            ]
            proof_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_PROOF"] = str(proof_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("governed_consequence_update", result.stderr)

    def test_verifier_fails_when_generated_proof_drops_reputation_marker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-reputation-marker-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            payload = json.loads(
                (REPO_ROOT / ".codex-studio" / "published" / "HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json").read_text(
                    encoding="utf-8"
                )
            )
            marker = (
                'reputationConsequencePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_action", '
                'StringComparison.Ordinal) && item.Summary.Contains("Review reputation fallout", StringComparison.Ordinal))'
            )
            payload["required_markers"]["campaign_session_recover_recap"] = [
                item for item in payload["required_markers"]["campaign_session_recover_recap"] if item != marker
            ]
            proof_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_PROOF"] = str(proof_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Review reputation fallout", result.stderr)

    def test_verifier_fails_when_smoke_drops_canonical_downtime_route_guard(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-downtime-route-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            smoke_path.write_text(
                smoke_text.replace(
                    'Assert(downtimeConsequencePayload.Receipts.Any(item => string.Equals(item.SourceKind, "return_loop_route", StringComparison.Ordinal) && string.Equals(item.ReceiptId, "/account/work#aftermath-packages", StringComparison.Ordinal)), "campaign spine consequence api should default downtime return-loop routes onto the governed aftermath rail.");',
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/account/work#aftermath-packages", result.stderr)

    def test_verifier_fails_when_controller_drops_campaign_memory_read_api(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-memory-api-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/CampaignSpineController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    '[HttpGet("me/workspaces/{workspaceId}/campaign-memory")]',
                    '[HttpGet("me/workspaces/{workspaceId}/campaign-memory-disabled")]',
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[HttpGet("me/workspaces/{workspaceId}/campaign-memory")]', result.stderr)

    def test_verifier_fails_when_controller_drops_consequence_truth_read_api(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-truth-api-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/CampaignSpineController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    '[HttpGet("me/workspaces/{workspaceId}/consequence-truth")]',
                    '[HttpGet("me/workspaces/{workspaceId}/consequence-truth-disabled")]',
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[HttpGet("me/workspaces/{workspaceId}/consequence-truth")]', result.stderr)

    def test_verifier_fails_when_smoke_drops_consequence_listing_api_guard(self) -> None:
        with tempfile.TemporaryDirectory(prefix="campaign-consequence-listing-api-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            smoke_path.write_text(
                smoke_text.replace(
                    'Assert(consequencesListPayload?.Any(item => string.Equals(item.Kind, "aftermath", StringComparison.Ordinal) && item.Receipts.Any(receipt => string.Equals(receipt.SourceKind, "governed_aftermath_package", StringComparison.Ordinal))) == true, "campaign spine consequence listing api should surface aftermath consequence truth with durable package receipts.");',
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("consequence listing api", result.stderr)

    @staticmethod
    def copy_sources(temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    @staticmethod
    def run_verifier(temp_root: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_CAMPAIGN_CONSEQUENCE_TRUTH_ROOT"] = str(temp_root)
        return subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
