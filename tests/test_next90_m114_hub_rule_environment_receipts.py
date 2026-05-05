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
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m114_hub_rule_environment_receipts.py"
MATERIALIZER = REPO_ROOT / "scripts" / "materialize_hub_local_release_proof.py"
PACKAGE_ID = "next90-m114-hub-rule-environment-receipts"
FRONTIER_ID = 4934642390
DO_NOT_REOPEN_REASON = (
    "M114 chummer6-hub rule-environment receipts are complete; future shards must verify this package receipt, "
    "registry row, queue row, and design-queue row instead of reopening the campaign/support/install-aware receipt lane."
)
SOURCE_FILES = [
    "Chummer.Control.Contracts/SupportContracts.cs",
    "Chummer.Run.Api/Services/Support/SupportAssistantService.cs",
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
    "scripts/materialize_hub_local_release_proof.py",
    "scripts/verify_next90_m114_hub_rule_environment_receipts.py",
    "scripts/ai/verify.sh",
    "tests/test_hub_local_release_proof_native_support_route.py",
    "tests/test_next90_m114_hub_rule_environment_receipts.py",
    "tests/RunServicesSmoke/Program.cs",
]


class Next90M114HubRuleEnvironmentReceiptsProofTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_m114_rule_environment_receipts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m114-accepts-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            verifier_paths = self.prepare_verifier_inputs(temp_root)
            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("rule-environment receipt proof passed", result.stdout)

    def test_verifier_fails_when_rules_truth_receipt_link_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m114-rules-receipt-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            service_path = temp_root / "Chummer.Run.Api/Services/Support/SupportAssistantService.cs"
            service_text = service_path.read_text(encoding="utf-8")
            service_path.write_text(
                service_text.replace("ReceiptId: entry.ExplainEntryId))", "ReceiptId: null))"),
                encoding="utf-8",
            )

            verifier_paths = self.prepare_verifier_inputs(temp_root)
            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ReceiptId: entry.ExplainEntryId))", result.stderr)

    def test_verifier_fails_when_support_citation_contract_drops_receipt_id(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m114-contract-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            contract_path = temp_root / "Chummer.Control.Contracts/SupportContracts.cs"
            contract_text = contract_path.read_text(encoding="utf-8")
            contract_path.write_text(
                contract_text.replace("    string? Href = null,\n    string? ReceiptId = null);", "    string? Href = null);"),
                encoding="utf-8",
            )

            verifier_paths = self.prepare_verifier_inputs(temp_root)
            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("string? ReceiptId = null);", result.stderr)

    def test_verifier_fails_when_queue_work_task_id_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m114-queue-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            verifier_paths = self.prepare_verifier_inputs(temp_root)
            queue_path = temp_root / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            payload = self.build_queue_payload()
            payload["items"][0]["work_task_id"] = "114.queue-drift"
            queue_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(
                temp_root,
                queue_staging_path=queue_path,
                design_queue_staging_path=verifier_paths["design_queue_staging_path"],
                successor_registry_path=verifier_paths["successor_registry_path"],
                local_release_proof_path=verifier_paths["local_release_proof_path"],
                served_release_proof_path=verifier_paths["served_release_proof_path"],
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("work_task_id must be '114.3'", result.stderr)

    def test_ai_verify_script_runs_m114_receipt_proof(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/verify_next90_m114_hub_rule_environment_receipts.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m114_hub_rule_environment_receipts.py", verify_script)

    def test_verifier_fails_when_release_proof_duplicates_m114_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m114-duplicate-receipt-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            verifier_paths = self.prepare_verifier_inputs(temp_root)
            proof_path = verifier_paths["local_release_proof_path"]
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            duplicate = next(
                receipt
                for receipt in proof["proof_receipts"]
                if receipt.get("package_id") == PACKAGE_ID
                and receipt.get("receipt_id") == "campaign_rule_environment_receipts"
            )
            proof["proof_receipts"].append(dict(duplicate))
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
            verifier_paths["served_release_proof_path"].write_text(
                proof_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate", result.stderr)

    def test_verifier_fails_when_release_proof_loses_m114_evidence_marker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m114-evidence-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            verifier_paths = self.prepare_verifier_inputs(temp_root)
            proof_path = verifier_paths["local_release_proof_path"]
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            for receipt in proof["proof_receipts"]:
                if receipt.get("package_id") == PACKAGE_ID and receipt.get("receipt_id") == "support_rule_environment_receipts":
                    receipt["evidence"] = receipt["evidence"][1:]
                    break
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
            verifier_paths["served_release_proof_path"].write_text(
                proof_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("evidence missing marker", result.stderr)

    def test_materialized_release_proof_includes_m114_rule_environment_receipts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m114-proof-") as temp_dir:
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
        self.assertEqual(114, package["milestone_id"])
        self.assertEqual("114.3", package["work_task_id"])
        self.assertEqual("complete", package["status"])
        self.assertEqual(FRONTIER_ID, package["frontier_id"])
        self.assertEqual("verify_closed_package_only", package["completion_action"])
        self.assertEqual(DO_NOT_REOPEN_REASON, package["do_not_reopen_reason"])

        receipts = {
            receipt.get("receipt_id"): receipt
            for receipt in proof["proof_receipts"]
            if receipt.get("package_id") == PACKAGE_ID
        }
        self.assertIn("campaign_rule_environment_receipts", receipts)
        self.assertIn("support_rule_environment_receipts", receipts)
        self.assertIn("install_aware_support_receipts", receipts)
        self.assertIn("/api/v1/campaign-spine/me/rules/{entryId}", receipts["campaign_rule_environment_receipts"]["routes"])
        self.assertIn("/api/v1/support/cases/assistant", receipts["support_rule_environment_receipts"]["routes"])
        self.assertIn("/account/access", receipts["install_aware_support_receipts"]["routes"])

    def copy_sources(self, temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            destination = temp_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

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
            "queue_staging_path": queue_path,
            "design_queue_staging_path": design_queue_path,
            "successor_registry_path": registry_path,
            "local_release_proof_path": local_proof_path,
            "served_release_proof_path": served_proof_path,
        }

    def materialize_proof(self, proof_path: Path) -> None:
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

    def run_verifier(
        self,
        temp_root: Path,
        *,
        queue_staging_path: Path,
        design_queue_staging_path: Path,
        successor_registry_path: Path,
        local_release_proof_path: Path,
        served_release_proof_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "CHUMMER_NEXT90_M114_ROOT": str(temp_root),
                "CHUMMER_NEXT90_M114_QUEUE_STAGING": str(queue_staging_path),
                "CHUMMER_NEXT90_M114_DESIGN_QUEUE_STAGING": str(design_queue_staging_path),
                "CHUMMER_NEXT90_M114_SUCCESSOR_REGISTRY": str(successor_registry_path),
                "CHUMMER_NEXT90_M114_LOCAL_RELEASE_PROOF": str(local_release_proof_path),
                "CHUMMER_NEXT90_M114_SERVED_RELEASE_PROOF": str(served_release_proof_path),
            }
        )
        return subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def build_queue_payload() -> dict[str, object]:
        return {
            "items": [
                {
                    "title": "Keep campaign, support, and install-aware diagnostics tied to the same rule-environment receipts",
                    "task": "Keep campaign, support, and install-aware diagnostics tied to the same rule-environment receipts.",
                    "package_id": PACKAGE_ID,
                    "work_task_id": "114.3",
                    "milestone_id": 114,
                    "frontier_id": FRONTIER_ID,
                    "status": "complete",
                    "completion_action": "verify_closed_package_only",
                    "do_not_reopen_reason": DO_NOT_REOPEN_REASON,
                    "wave": "W12",
                    "repo": "chummer6-hub",
                    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
                    "owned_surfaces": [
                        "campaign_rule_environment_receipts",
                        "support_rule_environment_receipts",
                        "install_aware_support_receipts",
                    ],
                }
            ]
        }

    @staticmethod
    def build_registry_payload() -> dict[str, object]:
        return {
            "milestones": [
                {
                    "id": 114,
                    "title": "Rule-environment studio and explain receipts everywhere",
                    "status": "in_progress",
                    "work_tasks": [
                        {
                            "id": "114.3",
                            "owner": "chummer6-hub",
                            "title": "Keep campaign, support, and install-aware diagnostics tied to the same rule-environment receipts",
                            "status": "complete",
                            "evidence": [
                                "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/Community/CampaignSpineService.cs projects rules navigator answers with stable ExplainEntryId values, before/after diffs, and rule-environment studio lifecycle posture on signed-in campaign surfaces.",
                                "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/Support/SupportAssistantService.cs forwards RulesNavigator ExplainEntryId values into support citations and install-aware build citations so assistant answers stay grounded in the same campaign and build receipt lane.",
                                "python3 scripts/verify_next90_m114_hub_rule_environment_receipts.py exits 0.",
                                "python3 -m unittest tests/test_next90_m114_hub_rule_environment_receipts.py exits 0 with ran=8 failed=0.",
                            ],
                        }
                    ],
                }
            ]
        }


if __name__ == "__main__":
    unittest.main()
