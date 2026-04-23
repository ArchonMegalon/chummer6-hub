from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_install_aware_support_concierge.py"
SOURCE_FILES = [
    "Chummer.Run.Api/Services/Support/SupportConciergePacketService.cs",
    "Chummer.Run.Api/Controllers/SupportCasesController.cs",
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
    "tests/RunServicesVerification/SupportCrashVerification.cs",
    "scripts/materialize_hub_local_release_proof.py",
    "scripts/ai/verify.sh",
    "scripts/verify_install_aware_support_concierge.py",
    "tests/test_install_aware_support_concierge.py",
]


class InstallAwareSupportConciergeProofTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_support_concierge(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("install-aware support concierge proof passed", result.stdout)

    def test_verifier_fails_when_installed_build_receipt_truth_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="support-concierge-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            service_path = temp_root / "Chummer.Run.Api/Services/Support/SupportConciergePacketService.cs"
            service_text = service_path.read_text(encoding="utf-8")
            service_path.write_text(
                service_text.replace("Installed build receipt:", "Installed build marker removed:"),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Installed build receipt:", result.stderr)

    def test_verifier_fails_when_authenticated_packet_route_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="support-concierge-route-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/SupportCasesController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace('[HttpGet("{caseId}/concierge")]', '[HttpGet("{caseId}/packet-removed")]'),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[HttpGet("{caseId}/concierge")]', result.stderr)

    def test_verifier_fails_when_closed_queue_authority_is_not_explicit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="support-concierge-queue-") as temp_dir:
            queue_path = Path(temp_dir) / "queue.yaml"
            queue_path.write_text(
                """
items:
  - title: Emit install-aware release and support concierge packets from installed-build truth
    task: Compile support closure and release explainer packets from installed build, channel, and support-case truth.
    package_id: next90-m111-hub-support-concierge
    milestone_id: 111
    frontier_id: 1
    wave: W9
    repo: chummer6-hub
    status: in_progress
    landed_commit: stale123
    completion_action: keep_working
    do_not_reopen_reason: ""
    allowed_paths:
      - Chummer.Run.Api
      - scripts
      - tests
    owned_surfaces:
      - install_aware_support_concierge
      - release_concierge:hub
""",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["CHUMMER_SUPPORT_CONCIERGE_QUEUE_STAGING"] = str(queue_path)
            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("frontier_id must be 2746902416", result.stderr)
        self.assertIn("status must be 'complete'", result.stderr)
        self.assertIn("landed_commit must be '3fb14923'", result.stderr)
        self.assertIn("completion_action must be 'verify_closed_package_only'", result.stderr)
        self.assertIn("do_not_reopen_reason must tell future shards to verify instead of reopening", result.stderr)

    def test_verifier_fails_when_design_queue_public_wrapper_surface_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="support-concierge-design-queue-") as temp_dir:
            queue_path = Path(temp_dir) / "design-queue.yaml"
            queue_path.write_text(
                """
items:
  - title: Emit install-aware release, support, and public concierge packets from installed-build truth
    task: Compile support closure and release explainer packets, plus public trust wrapper flows with first-party fallbacks, from installed build, channel, and support-case truth.
    package_id: next90-m111-hub-support-concierge
    milestone_id: 111
    frontier_id: 2746902416
    wave: W9
    repo: chummer6-hub
    status: complete
    allowed_paths:
      - Chummer.Run.Api
      - scripts
      - tests
    owned_surfaces:
      - install_aware_support_concierge
      - release_concierge:hub
""",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["CHUMMER_SUPPORT_CONCIERGE_DESIGN_QUEUE_STAGING"] = str(queue_path)
            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("design queue next90-m111-hub-support-concierge owned_surfaces drifted", result.stderr)

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
        env["CHUMMER_SUPPORT_CONCIERGE_ROOT"] = str(temp_root)
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
