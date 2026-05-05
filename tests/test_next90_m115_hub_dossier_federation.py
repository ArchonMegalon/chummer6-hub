from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m115_hub_dossier_federation.py"
SOURCE_FILES = [
    "Chummer.Run.Api/Contracts/CampaignFederationContracts.cs",
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs",
    "Chummer.Run.Api/Services/Community/CampaignFederationOrchestrationService.cs",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/ai/verify.sh",
    "scripts/verify_next90_m115_hub_dossier_federation.py",
    "tests/test_next90_m115_hub_dossier_federation.py",
]


class Next90M115HubDossierFederationTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_federation_lane(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m115 hub dossier federation proof passed", result.stdout)

    def test_verify_script_runs_m115_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/verify_next90_m115_hub_dossier_federation.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m115_hub_dossier_federation.py", verify_script)

    def test_verifier_fails_when_queue_row_reopens(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m115-queue-") as temp_dir:
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
                if item.get("package_id") == "next90-m115-hub-dossier-federation-orchestration":
                    item["status"] = "in_progress"
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status must be 'complete'", result.stderr)

    def test_verifier_fails_when_controller_drops_federation_route(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m115-controller-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/CampaignSpineController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace('[HttpPost("me/workspaces/{workspaceId}/federation-batches")]', '[HttpPost("me/workspaces/{workspaceId}/federation-disabled")]'),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[HttpPost("me/workspaces/{workspaceId}/federation-batches")]', result.stderr)

    def test_verifier_fails_when_service_drops_campaign_recap_source_pack_lane(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m115-service-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            service_path = temp_root / "Chummer.Run.Api/Services/Community/CampaignFederationOrchestrationService.cs"
            service_text = service_path.read_text(encoding="utf-8")
            service_path.write_text(
                service_text.replace('? "campaign_recap"', '? "creator_publication"'),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("campaign_recap", result.stderr)

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
        env["CHUMMER_NEXT90_M115_HUB_DOSSIER_FEDERATION_ROOT"] = str(temp_root)
        if queue_path is not None:
            env["CHUMMER_NEXT90_M115_HUB_DOSSIER_FEDERATION_QUEUE_STAGING"] = str(queue_path)
        if design_queue_path is not None:
            env["CHUMMER_NEXT90_M115_HUB_DOSSIER_FEDERATION_DESIGN_QUEUE_STAGING"] = str(design_queue_path)
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_next90_m115_hub_dossier_federation.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
