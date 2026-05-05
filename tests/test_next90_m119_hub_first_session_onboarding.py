from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m119_hub_first_session_onboarding.py"
SOURCE_FILES = [
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs",
    "Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
    "Chummer.Run.Api/Views/PublicLanding/Landing.cshtml",
    "Chummer.Run.Api/Views/PublicLanding/Home.cshtml",
    "Chummer.Run.Api/Views/Accounts/Account.cshtml",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/materialize_hub_local_release_proof.py",
    "scripts/verify_next90_m119_hub_first_session_onboarding.py",
    "tests/test_hub_local_release_proof_native_support_route.py",
    "scripts/ai/verify.sh",
    ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json",
]


class Next90M119HubFirstSessionOnboardingTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_first_session_onboarding_lane(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m119 hub first-session onboarding proof passed", result.stdout)

    def test_verify_script_runs_m119_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/verify_next90_m119_hub_first_session_onboarding.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m119_hub_first_session_onboarding.py", verify_script)

    def test_verifier_fails_when_queue_status_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m119-queue-") as temp_dir:
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
                if item.get("package_id") == "next90-m119-hub-first-session-onboarding":
                    item["status"] = "complete"
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status must be 'in_progress'", result.stderr)

    def test_verifier_fails_when_home_loses_starter_endpoint(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m119-home-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            home_path = temp_root / "Chummer.Run.Api/Views/PublicLanding/Home.cshtml"
            home_text = home_path.read_text(encoding="utf-8")
            home_path.write_text(
                home_text.replace("/api/v1/campaign-spine/me/workspaces/starter", "/api/v1/campaign-spine/me/workspaces/new"),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/api/v1/campaign-spine/me/workspaces/starter", result.stderr)

    def test_verifier_fails_when_account_loses_install_support_followthrough(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m119-account-support-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            account_path = temp_root / "Chummer.Run.Api/Views/Accounts/Account.cshtml"
            account_text = account_path.read_text(encoding="utf-8")
            account_path.write_text(
                account_text.replace("Open install support", "Open help"),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Open install support", result.stderr)

    def test_verifier_fails_when_release_proof_drops_first_session_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m119-proof-receipt-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            proof_text = proof_path.read_text(encoding="utf-8")
            proof_path.write_text(
                proof_text.replace('"receipt_id": "first_playable_session:onboarding"', '"receipt_id": "first_playable_session:onboarding_removed"'),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing receipt first_playable_session:onboarding", result.stderr)

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
        env["CHUMMER_NEXT90_M119_ROOT"] = str(temp_root)
        if queue_path is not None:
            env["CHUMMER_NEXT90_M119_QUEUE_STAGING"] = str(queue_path)
        if design_queue_path is not None:
            env["CHUMMER_NEXT90_M119_DESIGN_QUEUE_STAGING"] = str(design_queue_path)
        env["CHUMMER_NEXT90_M119_LOCAL_RELEASE_PROOF"] = str(temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json")
        env["CHUMMER_NEXT90_M119_SERVED_RELEASE_PROOF"] = str(temp_root / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json")
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_next90_m119_hub_first_session_onboarding.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
