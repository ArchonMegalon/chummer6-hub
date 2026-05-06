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
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m116_hub_creator_publication.py"
SOURCE_FILES = [
    ".codex-design/product/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    "Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "Chummer.Run.Api/Controllers/AccountsController.cs",
    "Chummer.Run.Api/Services/Community/CreatorPublicationRegistryBridge.cs",
    "Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs",
    "Chummer.Run.Api/Views/Accounts/Account.cshtml",
    "Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml",
    ".codex-studio/published/NEXT90_M116_HUB_CREATOR_PUBLICATION.generated.json",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/ai/verify.sh",
    "scripts/verify_next90_m116_hub_creator_publication.py",
    "tests/test_next90_m116_hub_creator_publication.py",
]


class Next90M116HubCreatorPublicationTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_creator_publication_lane(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m116 hub creator publication proof passed", result.stdout)

    def test_verify_script_runs_m116_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/verify_next90_m116_hub_creator_publication.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m116_hub_creator_publication.py", verify_script)

    def test_verifier_fails_when_queue_row_reopens(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-queue-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            queue_path = temp_root / "fleet-queue.yaml"
            design_queue_path = temp_root / "design-queue.yaml"
            shutil.copyfile(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
                queue_path,
            )
            shutil.copyfile(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
                design_queue_path,
            )
            queue_payload = yaml.safe_load(queue_path.read_text(encoding="utf-8"))
            for item in queue_payload["items"]:
                if item.get("package_id") == "next90-m116-hub-creator-publication":
                    item["status"] = "in_progress"
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status must be 'complete'", result.stderr)

    def test_verifier_fails_when_design_queue_row_drifts_from_fleet_queue(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-queue-parity-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            queue_path = temp_root / "fleet-queue.yaml"
            design_queue_path = temp_root / "design-queue.yaml"
            shutil.copyfile(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
                queue_path,
            )
            shutil.copyfile(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
                design_queue_path,
            )
            design_queue_payload = yaml.safe_load(design_queue_path.read_text(encoding="utf-8"))
            for item in design_queue_payload["items"]:
                if item.get("package_id") == "next90-m116-hub-creator-publication":
                    item["owned_surfaces"] = ["creator_publication:discovery"]
                    break
            design_queue_path.write_text(yaml.safe_dump(design_queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fleet and design queue rows for next90-m116-hub-creator-publication must match exactly", result.stderr)

    def test_verifier_fails_when_complete_queue_row_looks_open(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-premature-close-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            queue_path = temp_root / "fleet-queue.yaml"
            design_queue_path = temp_root / "design-queue.yaml"
            shutil.copyfile(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
                queue_path,
            )
            shutil.copyfile(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
                design_queue_path,
            )
            queue_payload = yaml.safe_load(queue_path.read_text(encoding="utf-8"))
            for item in queue_payload["items"]:
                if item.get("package_id") == "next90-m116-hub-creator-publication":
                    item.pop("completion_action", None)
                    item.pop("do_not_reopen_reason", None)
                    item.pop("proof", None)
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be 'verify_closed_package_only'", result.stderr)

    def test_verifier_fails_when_queue_proof_widens_beyond_closed_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-proof-widening-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            queue_path = temp_root / "fleet-queue.yaml"
            design_queue_path = temp_root / "design-queue.yaml"
            shutil.copyfile(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
                queue_path,
            )
            shutil.copyfile(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
                design_queue_path,
            )
            queue_payload = yaml.safe_load(queue_path.read_text(encoding="utf-8"))
            for item in queue_payload["items"]:
                if item.get("package_id") == "next90-m116-hub-creator-publication":
                    item["proof"].append("/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/PublicLandingService.cs")
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("proof must match the closed-package receipt exactly", result.stderr)

    def test_verifier_fails_when_successor_registry_task_lacks_closed_status_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-successor-registry-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            successor_registry_path = temp_root / "successor-registry.yaml"
            mirror_registry_path = temp_root / ".codex-design/product/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            shutil.copyfile(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
                successor_registry_path,
            )
            registry_payload = yaml.safe_load(successor_registry_path.read_text(encoding="utf-8"))
            for milestone in registry_payload["milestones"]:
                if milestone.get("id") == 116:
                    milestone["status"] = "in_progress"
                    for task in milestone["work_tasks"]:
                        if str(task.get("id")) == "116.1":
                            task.pop("status", None)
                            task.pop("evidence", None)
                            break
                    break
            successor_registry_path.write_text(yaml.safe_dump(registry_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(
                temp_root,
                successor_registry_path=successor_registry_path,
                local_mirror_successor_registry_path=mirror_registry_path,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("milestone 116 status must be 'complete'", result.stderr)
        self.assertIn("work task 116.1 status must be 'complete'", result.stderr)
        self.assertIn("work task 116.1 evidence must be a list", result.stderr)

    def test_verifier_fails_when_repo_local_successor_registry_drifts_from_canonical(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-successor-registry-parity-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            successor_registry_path = temp_root / "successor-registry.yaml"
            mirror_registry_path = temp_root / ".codex-design/product/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            shutil.copyfile(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
                successor_registry_path,
            )
            mirror_payload = yaml.safe_load(mirror_registry_path.read_text(encoding="utf-8"))
            for milestone in mirror_payload["milestones"]:
                if milestone.get("id") == 116:
                    for task in milestone["work_tasks"]:
                        if str(task.get("id")) == "116.1":
                            task["evidence"] = ["drifted"]
                            break
                    break
            mirror_registry_path.write_text(yaml.safe_dump(mirror_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(
                temp_root,
                successor_registry_path=successor_registry_path,
                local_mirror_successor_registry_path=mirror_registry_path,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical and repo-local successor registry work task 116.1 must match exactly", result.stderr)

    def test_verifier_fails_when_correction_resubmission_copy_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-account-view-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            account_view_path = temp_root / "Chummer.Run.Api/Views/Accounts/Account.cshtml"
            account_view_text = account_view_path.read_text(encoding="utf-8")
            account_view_path.write_text(
                account_view_text.replace("Resubmit corrected packet", "Submit for review"),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Resubmit corrected packet", result.stderr)

    def test_verifier_fails_when_correction_pass_proof_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-correction-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            smoke_path.write_text(
                smoke_text.replace(
                    'Assert(resubmittedDossierPublicationDetailModel?.SelectedCreatorPublicationDraftDetail?.LatestModerationNotes?.Contains("Correction pass refreshed", StringComparison.OrdinalIgnoreCase) == true, "resubmitted dossier publications should stamp the correction-pass resubmission note onto the governed moderation lane.");',
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("correction-pass resubmission note", result.stderr)

    def test_verifier_fails_when_rejected_publication_public_detail_guard_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-public-fail-closed-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            smoke_path.write_text(
                smoke_text.replace(
                    'Assert(await controller.CreatorPublicationDetailPage(dossierPublicationId, CancellationToken.None) is NotFoundResult, "guest creator-publication detail should fail closed while a dossier packet is still rejected on the governed moderation lane.");',
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fail closed while a dossier packet is still rejected", result.stderr)

    def test_verifier_fails_when_rejected_publication_public_api_guard_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-public-api-fail-closed-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            smoke_path.write_text(
                smoke_text.replace(
                    'Assert(await controller.CreatorPublicationDetailApi(dossierPublicationId, locale: "en-us", CancellationToken.None) is NotFoundResult, "creator publication detail api should fail closed while a dossier packet is still rejected on the governed moderation lane.");',
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("detail api should fail closed while a dossier packet is still rejected", result.stderr)

    def test_verifier_fails_when_manifest_authority_guard_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-manifest-authority-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            discovery_path = temp_root / "Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs"
            discovery_text = discovery_path.read_text(encoding="utf-8")
            discovery_path.write_text(
                discovery_text.replace(
                    'description.Contains("Manifest authority: approved-shared-publication-manifest;", StringComparison.Ordinal)',
                    'description.Contains("Manifest authority:", StringComparison.Ordinal)',
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Manifest authority: approved-shared-publication-manifest;", result.stderr)

    def test_verifier_fails_when_manifest_blocking_message_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-blocking-copy-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            bridge_path = temp_root / "Chummer.Run.Api/Services/Community/CreatorPublicationRegistryBridge.cs"
            bridge_text = bridge_path.read_text(encoding="utf-8")
            bridge_path.write_text(
                bridge_text.replace(
                    "Creator publication moderation requires an approved manifest-backed audit receipt before submission, correction, approval, or publication.",
                    "Creator publication moderation requires a receipt before publication.",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("approved manifest-backed audit receipt", result.stderr)

    def test_verifier_fails_when_discovery_trust_ranking_order_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-trust-ranking-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            discovery_path = temp_root / "Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs"
            discovery_text = discovery_path.read_text(encoding="utf-8")
            discovery_path.write_text(
                discovery_text.replace(
                    ".OrderByDescending(item => RankTrustBand(item.TrustBand))",
                    ".OrderBy(static item => item.Title, StringComparer.OrdinalIgnoreCase)",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".OrderByDescending(item => RankTrustBand(item.TrustBand))", result.stderr)

    def test_verifier_fails_when_public_artifact_shelf_contract_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-artifact-shelf-api-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            smoke_path.write_text(
                smoke_text.replace(
                    'Assert(string.Equals(guestArtifactShelfApiDocument.RootElement.GetProperty("contractName").GetString(), "chummer.run.public_artifact_shelf.v2", StringComparison.Ordinal), "artifact shelf api should expose the governed public artifact shelf contract.");',
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("public artifact shelf contract", result.stderr)

    def test_verifier_fails_when_public_creator_detail_contract_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-publication-detail-api-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            smoke_path.write_text(
                smoke_text.replace(
                    'Assert(string.Equals(publicCreatorDetailApiDocument.RootElement.GetProperty("contractName").GetString(), "chummer.run.public_artifact_shelf.publication.v1", StringComparison.Ordinal), "creator publication detail api should expose the governed publication detail contract.");',
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("governed publication detail contract", result.stderr)

    def test_verifier_fails_when_generated_proof_receipt_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-generated-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            generated_proof_path = temp_root / ".codex-studio/published/NEXT90_M116_HUB_CREATOR_PUBLICATION.generated.json"
            generated_proof = yaml.safe_load(generated_proof_path.read_text(encoding="utf-8"))
            generated_proof["evidence"]["completionAction"] = "reopen_package"
            generated_proof_path.write_text(json.dumps(generated_proof, indent=2) + "\n", encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("evidence.completionAction must be 'verify_closed_package_only'", result.stderr)

    def test_verifier_fails_when_generated_proof_command_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-generated-proof-command-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            generated_proof_path = temp_root / ".codex-studio/published/NEXT90_M116_HUB_CREATOR_PUBLICATION.generated.json"
            generated_proof = yaml.safe_load(generated_proof_path.read_text(encoding="utf-8"))
            generated_proof["evidence"]["proofCommands"]["verifyScript"] = "python3 scripts/verify_something_else.py"
            generated_proof_path.write_text(json.dumps(generated_proof, indent=2) + "\n", encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "evidence.proofCommands.verifyScript must be 'python3 scripts/verify_next90_m116_hub_creator_publication.py'",
            result.stderr,
        )

    def test_verifier_fails_when_generated_proof_files_widen_beyond_closed_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m116-generated-proof-files-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            generated_proof_path = temp_root / ".codex-studio/published/NEXT90_M116_HUB_CREATOR_PUBLICATION.generated.json"
            generated_proof = yaml.safe_load(generated_proof_path.read_text(encoding="utf-8"))
            generated_proof["evidence"]["proofFiles"].append(
                "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/PublicLandingService.cs"
            )
            generated_proof_path.write_text(json.dumps(generated_proof, indent=2) + "\n", encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("evidence.proofFiles must match the closed-package receipt exactly", result.stderr)

    @staticmethod
    def copy_sources(temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def run_verifier(
        self,
        temp_root: Path,
        *,
        queue_path: Path | None = None,
        design_queue_path: Path | None = None,
        successor_registry_path: Path | None = None,
        local_mirror_successor_registry_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_NEXT90_M116_HUB_CREATOR_PUBLICATION_ROOT"] = str(temp_root)
        if queue_path is not None:
            env["CHUMMER_NEXT90_M116_HUB_CREATOR_PUBLICATION_QUEUE_STAGING"] = str(queue_path)
        if design_queue_path is not None:
            env["CHUMMER_NEXT90_M116_HUB_CREATOR_PUBLICATION_DESIGN_QUEUE_STAGING"] = str(design_queue_path)
        if successor_registry_path is not None:
            env["CHUMMER_NEXT90_M116_HUB_CREATOR_PUBLICATION_SUCCESSOR_REGISTRY"] = str(successor_registry_path)
        if local_mirror_successor_registry_path is not None:
            env["CHUMMER_NEXT90_M116_HUB_CREATOR_PUBLICATION_LOCAL_MIRROR_SUCCESSOR_REGISTRY"] = str(
                local_mirror_successor_registry_path
            )
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_next90_m116_hub_creator_publication.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
