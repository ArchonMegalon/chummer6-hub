from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m118_hub_organizer_ops.py"
SOURCE_FILES = [
    "Chummer.Run.Api/Contracts/OrganizerOpsContracts.cs",
    "Chummer.Campaign.Contracts/CampaignContracts.cs",
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs",
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
    "Chummer.Run.Api/Views/Accounts/Account.cshtml",
    "Chummer.Run.Api/Views/PublicLanding/Home.cshtml",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/ai/verify.sh",
    "scripts/verify_next90_m118_hub_organizer_ops.py",
    "tests/test_next90_m118_hub_organizer_ops.py",
]


class Next90M118HubOrganizerOpsTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_organizer_ops(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m118 hub organizer ops proof passed", result.stdout)

    def test_verify_script_runs_m118_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/verify_next90_m118_hub_organizer_ops.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m118_hub_organizer_ops.py", verify_script)

    def test_verifier_fails_when_queue_row_reopens_or_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m118-queue-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            queue_path = temp_root / "fleet-queue.yaml"
            shutil.copyfile(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
                queue_path,
            )
            queue_payload = yaml.safe_load(queue_path.read_text(encoding="utf-8"))
            for item in queue_payload["items"]:
                if item.get("package_id") == "next90-m118-hub-organizer-ops":
                    item["status"] = "complete"
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status must be 'in_progress'", result.stderr)

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

            result = self.run_verifier(temp_root)

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

            result = self.run_verifier(temp_root)

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

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GetMyOrganizerOperations", result.stderr)

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
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_ROOT"] = str(temp_root)
        if queue_path is not None:
            env["CHUMMER_NEXT90_M118_HUB_ORGANIZER_OPS_QUEUE_STAGING"] = str(queue_path)
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_next90_m118_hub_organizer_ops.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
