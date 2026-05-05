from __future__ import annotations

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
    "Chummer.Run.Api/Controllers/AccountsController.cs",
    "Chummer.Run.Api/Services/Community/CreatorPublicationRegistryBridge.cs",
    "Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs",
    "Chummer.Run.Api/Views/Accounts/Account.cshtml",
    "Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml",
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
                    item["status"] = "complete"
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status must be 'in_progress'", result.stderr)

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
        env["CHUMMER_NEXT90_M116_HUB_CREATOR_PUBLICATION_ROOT"] = str(temp_root)
        if queue_path is not None:
            env["CHUMMER_NEXT90_M116_HUB_CREATOR_PUBLICATION_QUEUE_STAGING"] = str(queue_path)
        if design_queue_path is not None:
            env["CHUMMER_NEXT90_M116_HUB_CREATOR_PUBLICATION_DESIGN_QUEUE_STAGING"] = str(design_queue_path)
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_next90_m116_hub_creator_publication.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
