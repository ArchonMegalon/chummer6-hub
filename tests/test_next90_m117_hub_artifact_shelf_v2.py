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
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m117_hub_artifact_shelf_v2.py"
PACKAGE_ID = "next90-m117-hub-artifact-shelf-v2"
SOURCE_FILES = [
    ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "Chummer.Run.Api/Services/Community/CreatorPublicationRegistryBridge.cs",
    "Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs",
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
    "Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs",
    "Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml",
    "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/materialize_hub_local_release_proof.py",
    "scripts/ai/verify.sh",
    "scripts/verify_next90_m117_hub_artifact_shelf_v2.py",
    "tests/test_next90_m117_hub_artifact_shelf_v2.py",
]
SUCCESSOR_REGISTRY_SOURCE = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml")
FLEET_QUEUE_SOURCE = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
DESIGN_QUEUE_SOURCE = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")


def load_yaml_fixture(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        package_marker = f"package_id: {PACKAGE_ID}"
        package_index = text.index(package_marker)
        start = text.rfind("\n- title:", 0, package_index)
        if start < 0:
            if not text.startswith("- title:"):
                raise
            start = 0
        else:
            start += 1

        end = text.find("\n- title:", package_index)
        if end < 0:
            end = len(text)

        block = text[start:end].rstrip() + "\n"
        payload = yaml.safe_load(block)
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
            raise
        return {"items": payload}


class Next90M117HubArtifactShelfV2Tests(unittest.TestCase):
    def test_verifier_accepts_repo_local_artifact_shelf_lane(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m117 hub artifact shelf v2 proof passed", result.stdout)

    def test_verify_script_runs_m117_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/verify_next90_m117_hub_artifact_shelf_v2.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m117_hub_artifact_shelf_v2.py", verify_script)

    def test_verifier_fails_when_queue_row_reopens_or_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-queue-") as temp_dir:
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
            queue_payload = load_yaml_fixture(queue_path)
            for item in queue_payload["items"]:
                if item.get("package_id") == "next90-m117-hub-artifact-shelf-v2":
                    item["status"] = "in_progress"
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status must be 'complete'", result.stderr)

    def test_verifier_fails_when_design_queue_row_drifts_from_fleet_queue(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-queue-parity-") as temp_dir:
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
            design_queue_payload = load_yaml_fixture(design_queue_path)
            for item in design_queue_payload["items"]:
                if item.get("package_id") == "next90-m117-hub-artifact-shelf-v2":
                    item["owned_surfaces"] = ["artifact_shelf:v2"]
                    break
            design_queue_path.write_text(yaml.safe_dump(design_queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fleet and design queue rows for next90-m117-hub-artifact-shelf-v2 must match exactly", result.stderr)

    def test_verifier_fails_when_complete_queue_row_loses_completion_action(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-premature-close-") as temp_dir:
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
            queue_payload = load_yaml_fixture(queue_path)
            for item in queue_payload["items"]:
                if item.get("package_id") == "next90-m117-hub-artifact-shelf-v2":
                    item.pop("completion_action", None)
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("completion_action must be 'verify_closed_package_only'", result.stderr)

    def test_verifier_fails_when_successor_registry_status_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-registry-status-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            successor_registry_path = temp_root / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            shutil.copyfile(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
                successor_registry_path,
            )
            registry_payload = yaml.safe_load(successor_registry_path.read_text(encoding="utf-8"))
            for milestone in registry_payload["milestones"]:
                if milestone.get("id") == 117:
                    milestone["status"] = "in_progress"
                    break
            successor_registry_path.write_text(yaml.safe_dump(registry_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, successor_registry_path=successor_registry_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("milestone 117 status must be 'complete'", result.stderr)

    def test_verifier_fails_when_successor_registry_work_task_title_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-registry-task-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            successor_registry_path = temp_root / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            shutil.copyfile(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
                successor_registry_path,
            )
            registry_payload = yaml.safe_load(successor_registry_path.read_text(encoding="utf-8"))
            for milestone in registry_payload["milestones"]:
                if milestone.get("id") != 117:
                    continue
                for work_task in milestone["work_tasks"]:
                    if str(work_task.get("id")) == "117.1":
                        work_task["title"] = "Artifact shelf task drifted"
                        break
                break
            successor_registry_path.write_text(yaml.safe_dump(registry_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, successor_registry_path=successor_registry_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("work task 117.1 title drifted", result.stderr)

    def test_verifier_fails_when_shelf_view_loses_creator_filter(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-shelf-view-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            shelf_view_path = temp_root / "Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml"
            shelf_view_text = shelf_view_path.read_text(encoding="utf-8")
            shelf_view_path.write_text(
                shelf_view_text.replace('"Creator view"', '"Creator lane"'),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('"Creator view"', result.stderr)

    def test_verifier_fails_when_shelf_view_loses_public_filter(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-shelf-public-view-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            shelf_view_path = temp_root / "Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml"
            shelf_view_text = shelf_view_path.read_text(encoding="utf-8")
            shelf_view_path.write_text(
                shelf_view_text.replace('"Public view"', '"Published lane"'),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('"Public view"', result.stderr)

    def test_verifier_fails_when_controller_stops_filtering_by_audience(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-controller-filter-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    "return AudienceContains(item.Audience, signedInArtifactView);",
                    "return true;",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("return AudienceContains(item.Audience, signedInArtifactView);", result.stderr)

    def test_verifier_fails_when_artifact_shelf_api_contract_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-artifact-shelf-api-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    'contractName = "chummer.run.public_artifact_shelf.v2"',
                    'contractName = "chummer.run.public_artifact_shelf.v1"',
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('contractName = "chummer.run.public_artifact_shelf.v2"', result.stderr)

    def test_verifier_fails_when_versioned_artifact_shelf_api_route_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-versioned-artifact-shelf-api-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    '[HttpGet("/api/v1/public/artifacts/shelf")]',
                    '[HttpGet("/api/public/artifacts/shelf")]',
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[HttpGet("/api/v1/public/artifacts/shelf")]', result.stderr)

    def test_verifier_fails_when_compat_artifact_shelf_api_route_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-compat-artifact-shelf-api-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    '[HttpGet("/api/public/artifacts/shelf")]',
                    '[HttpGet("/api/public/artifact-shelf")]',
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[HttpGet("/api/public/artifacts/shelf")]', result.stderr)

    def test_verifier_fails_when_publication_detail_api_route_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-publication-detail-api-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    '[HttpGet("artifacts/publications/{publicationId}")]',
                    '[HttpGet("artifacts/publication/{publicationId}")]',
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[HttpGet("artifacts/publications/{publicationId}")]', result.stderr)

    def test_verifier_fails_when_versioned_publication_detail_api_route_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-versioned-publication-detail-api-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    '[HttpGet("/api/v1/public/artifacts/publications/{publicationId}")]',
                    '[HttpGet("/api/public/artifacts/publications/{publicationId}")]',
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[HttpGet("/api/v1/public/artifacts/publications/{publicationId}")]', result.stderr)

    def test_verifier_fails_when_compat_publication_detail_api_route_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-compat-publication-detail-api-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    '[HttpGet("/api/public/artifacts/publications/{publicationId}")]',
                    '[HttpGet("/api/public/artifact-publications/{publicationId}")]',
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[HttpGet("/api/public/artifacts/publications/{publicationId}")]', result.stderr)

    def test_verifier_fails_when_public_creator_discovery_loses_manifest_authority_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-public-creator-discovery-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            discovery_path = temp_root / "Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs"
            discovery_text = discovery_path.read_text(encoding="utf-8")
            discovery_path.write_text(
                discovery_text.replace(
                    ".Where(static item => HasApprovedManifestAuthority(item.Draft, item.Detail))",
                    ".Where(static item => true)",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HasApprovedManifestAuthority(item.Draft, item.Detail)", result.stderr)

    def test_verifier_fails_when_smoke_public_view_guard_disappears(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-public-view-smoke-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            smoke_path.write_text(
                smoke_text.replace(
                    'Assert(string.Equals(publicArtifactsModel?.SignedInArtifactView, "public", StringComparison.Ordinal), "authenticated artifacts shelf should honor the explicit public view filter.");',
                    '// removed public view smoke guard',
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SignedInArtifactView, "public"', result.stderr)

    def test_verifier_fails_when_controller_drops_creator_publication_audience_label(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-controller-audience-label-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    'audienceLabel = PublicSurfaceStatus.AudienceLabel(string.Join(",", audience)),',
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('audienceLabel = PublicSurfaceStatus.AudienceLabel(string.Join(",", audience)),', result.stderr)

    def test_verifier_fails_when_release_proof_drops_public_artifact_view_surface(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-proof-surface-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            materializer_path = temp_root / "scripts/materialize_hub_local_release_proof.py"
            materializer_text = materializer_path.read_text(encoding="utf-8")
            materializer_path.write_text(
                materializer_text.replace(
                    '"artifact_view:public",\n',
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('"artifact_view:public"', result.stderr)

    def test_verifier_fails_when_release_proof_summary_stops_naming_public_view(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-proof-summary-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            local_proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            proof = json.loads(local_proof_path.read_text(encoding="utf-8"))
            for receipt in proof["proof_receipts"]:
                if receipt.get("package_id") == "next90-m117-hub-artifact-shelf-v2" and receipt.get("receipt_id") == "artifact_audience_filters":
                    receipt["summary"] = receipt["summary"].replace(
                        "personal, campaign, creator, or public",
                        "personal, campaign, or creator",
                    )
                    break
            local_proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
            served_proof_path = temp_root / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
            served_proof_path.write_text(local_proof_path.read_text(encoding="utf-8"), encoding="utf-8")

            result = self.run_verifier(
                temp_root,
                local_release_proof_path=local_proof_path,
                served_release_proof_path=served_proof_path,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("personal, campaign, creator, or public", result.stderr)

    def test_verifier_fails_when_release_proof_drops_creator_publication_detail_route(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-proof-route-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            materializer_path = temp_root / "scripts/materialize_hub_local_release_proof.py"
            materializer_text = materializer_path.read_text(encoding="utf-8")
            materializer_path.write_text(
                materializer_text.replace(
                    '                    "/artifacts/publications/{publicationId}",\n',
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('"/artifacts/publications/{publicationId}"', result.stderr)

    def test_verifier_fails_when_release_proof_loses_manifest_authority_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-proof-evidence-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            materializer_path = temp_root / "scripts/materialize_hub_local_release_proof.py"
            materializer_text = materializer_path.read_text(encoding="utf-8")
            materializer_path.write_text(
                materializer_text.replace(
                    "manifest-authority-backed before the shared shelf surfaces it.",
                    "ready before the shared shelf surfaces it.",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("manifest-authority-backed before the shared shelf surfaces it.", result.stderr)

    def test_verifier_fails_when_release_proof_drops_publication_detail_route(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-local-proof-route-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            local_proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            proof = json.loads(local_proof_path.read_text(encoding="utf-8"))
            for receipt in proof["proof_receipts"]:
                if receipt.get("package_id") == "next90-m117-hub-artifact-shelf-v2" and receipt.get("receipt_id") == "artifact_shelf:v2":
                    receipt["routes"] = [
                        route
                        for route in receipt["routes"]
                        if route != "/api/v1/public/artifacts/publications/{publicationId}"
                    ]
                    break
            local_proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
            served_proof_path = temp_root / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
            served_proof_path.write_text(local_proof_path.read_text(encoding="utf-8"), encoding="utf-8")

            result = self.run_verifier(
                temp_root,
                local_release_proof_path=local_proof_path,
                served_release_proof_path=served_proof_path,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("route missing '/api/v1/public/artifacts/publications/{publicationId}'", result.stderr)

    def test_verifier_fails_when_served_release_proof_drifts_from_repo_local_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-proof-parity-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            local_proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            served_proof_path = temp_root / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
            served_proof = json.loads(served_proof_path.read_text(encoding="utf-8"))
            for receipt in served_proof["proof_receipts"]:
                if receipt.get("package_id") == "next90-m117-hub-artifact-shelf-v2" and receipt.get("receipt_id") == "artifact_audience_filters":
                    receipt["summary"] = "artifact shelf proof drifted on the served rail"
                    break
            served_proof_path.write_text(json.dumps(served_proof, indent=2) + "\n", encoding="utf-8")

            result = self.run_verifier(
                temp_root,
                local_release_proof_path=local_proof_path,
                served_release_proof_path=served_proof_path,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("repo-local and served release proof receipt 'artifact_audience_filters' for next90-m117-hub-artifact-shelf-v2 must match exactly", result.stderr)

    def test_verifier_fails_when_served_release_proof_package_row_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-proof-package-parity-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            local_proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            served_proof_path = temp_root / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
            served_proof = json.loads(served_proof_path.read_text(encoding="utf-8"))
            served_proof["successor_queue_packages_by_id"]["next90-m117-hub-artifact-shelf-v2"]["owned_surfaces"] = [
                "artifact_shelf:v2"
            ]
            served_proof_path.write_text(json.dumps(served_proof, indent=2) + "\n", encoding="utf-8")

            result = self.run_verifier(
                temp_root,
                local_release_proof_path=local_proof_path,
                served_release_proof_path=served_proof_path,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("repo-local and served release proof package rows for next90-m117-hub-artifact-shelf-v2 must match exactly", result.stderr)

    def test_verifier_fails_when_release_proof_cites_active_run_markers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m117-proof-marker-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            local_proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            proof = json.loads(local_proof_path.read_text(encoding="utf-8"))
            for receipt in proof["proof_receipts"]:
                if receipt.get("package_id") == "next90-m117-hub-artifact-shelf-v2" and receipt.get("receipt_id") == "artifact_shelf:v2":
                    receipt["evidence"] = list(receipt.get("evidence", [])) + [
                        "TASK_LOCAL_TELEMETRY.generated.json was used as package evidence."
                    ]
                    break
            local_proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
            served_proof_path = temp_root / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
            served_proof_path.write_text(local_proof_path.read_text(encoding="utf-8"), encoding="utf-8")

            result = self.run_verifier(
                temp_root,
                local_release_proof_path=local_proof_path,
                served_release_proof_path=served_proof_path,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contains forbidden active-run proof marker 'TASK_LOCAL_TELEMETRY'", result.stderr)

    @staticmethod
    def copy_sources(temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

        shutil.copyfile(SUCCESSOR_REGISTRY_SOURCE, temp_root / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml")
        shutil.copyfile(FLEET_QUEUE_SOURCE, temp_root / "fleet-queue.yaml")
        shutil.copyfile(DESIGN_QUEUE_SOURCE, temp_root / "design-queue.yaml")

    def run_verifier(
        self,
        temp_root: Path,
        *,
        queue_path: Path | None = None,
        design_queue_path: Path | None = None,
        successor_registry_path: Path | None = None,
        local_release_proof_path: Path | None = None,
        served_release_proof_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_ROOT"] = str(temp_root)
        env["CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_QUEUE_STAGING"] = str(queue_path or (temp_root / "fleet-queue.yaml"))
        env["CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_DESIGN_QUEUE_STAGING"] = str(design_queue_path or (temp_root / "design-queue.yaml"))
        env["CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_SUCCESSOR_REGISTRY"] = str(successor_registry_path or (temp_root / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"))
        if local_release_proof_path is not None:
            env["CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_LOCAL_RELEASE_PROOF"] = str(local_release_proof_path)
        if served_release_proof_path is not None:
            env["CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_SERVED_RELEASE_PROOF"] = str(served_release_proof_path)
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_next90_m117_hub_artifact_shelf_v2.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
