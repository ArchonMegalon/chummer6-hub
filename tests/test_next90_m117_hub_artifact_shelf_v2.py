from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m117_hub_artifact_shelf_v2.py"
SOURCE_FILES = [
    "Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "Chummer.Run.Api/Services/Community/CreatorPublicationRegistryBridge.cs",
    "Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs",
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
    "Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs",
    "Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/materialize_hub_local_release_proof.py",
    "scripts/ai/verify.sh",
    "scripts/verify_next90_m117_hub_artifact_shelf_v2.py",
    "tests/test_next90_m117_hub_artifact_shelf_v2.py",
]


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
            queue_payload = yaml.safe_load(queue_path.read_text(encoding="utf-8"))
            for item in queue_payload["items"]:
                if item.get("package_id") == "next90-m117-hub-artifact-shelf-v2":
                    item["status"] = "complete"
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status must be 'in_progress'", result.stderr)

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
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_ROOT"] = str(temp_root)
        if queue_path is not None:
            env["CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_QUEUE_STAGING"] = str(queue_path)
        if design_queue_path is not None:
            env["CHUMMER_NEXT90_M117_HUB_ARTIFACT_SHELF_DESIGN_QUEUE_STAGING"] = str(design_queue_path)
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_next90_m117_hub_artifact_shelf_v2.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
