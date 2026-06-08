from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m113_hub_roster_ops.py"
SOURCE_FILES = [
    "Chummer.Run.Api/Contracts/CampaignMovementContracts.cs",
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs",
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
    "Chummer.Tests/CampaignMovementServiceTests.cs",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/materialize_campaign_os_local_proof.py",
    "scripts/materialize_next90_m113_hub_roster_ops_proof.py",
    "scripts/ai/verify.sh",
    "scripts/yaml.py",
    "scripts/verify_next90_m113_hub_roster_ops.py",
    "tests/test_next90_m113_hub_roster_ops.py",
    "yaml.py",
    ".codex-studio/published/NEXT90_M113_HUB_ROSTER_OPS.generated.json",
]


class Next90M113HubRosterOpsProofTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_roster_ops(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m113 hub roster ops proof passed", result.stdout)

    def test_verify_script_runs_m113_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")

        self.assertIn("python3 scripts/materialize_next90_m113_hub_roster_ops_proof.py", verify_script)
        self.assertIn("python3 scripts/verify_next90_m113_hub_roster_ops.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m113_hub_roster_ops.py", verify_script)
        self.assertIn(
            "run_slice_safe_dotnet_test CampaignMovementServiceTests",
            verify_script,
        )

    def test_verifier_fails_when_controller_drops_dossier_movement_post_api(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m113-controller-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/CampaignSpineController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace('[HttpPost("me/dossier-movements")]', '[HttpPost("me/dossier-movement-disabled")]'),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[HttpPost("me/dossier-movements")]', result.stderr)

    def test_verifier_fails_when_smoke_drops_target_scene_receipt_guard(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m113-smoke-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            smoke_path.write_text(
                smoke_text.replace(
                    'Assert(dossierMovementPayload.Receipts.Any(item => string.Equals(item.SourceKind, "target_scene", StringComparison.Ordinal)), "campaign spine dossier-movement api should emit a durable governed target-scene receipt.");',
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target_scene", result.stderr)

    def test_verifier_fails_when_materializer_drops_dossier_movement_marker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m113-materializer-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            materializer_path = temp_root / "scripts/materialize_next90_m113_hub_roster_ops_proof.py"
            materializer_text = materializer_path.read_text(encoding="utf-8")
            materializer_path.write_text(
                materializer_text.replace(
                    '"var dossierMovementResult = await campaignSpineController.MoveMyDossier(",\n',
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MoveMyDossier", result.stderr)

    def test_verifier_rejects_active_run_markers_in_generated_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m113-proof-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            payload = json.loads(
                (REPO_ROOT / ".codex-studio" / "published" / "NEXT90_M113_HUB_ROSTER_OPS.generated.json").read_text(
                    encoding="utf-8"
                )
            )
            payload["required_markers"]["campaign_group_event_movement"].append(
                "TASK_LOCAL_TELEMETRY.generated.json is forbidden completion proof."
            )
            proof_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_NEXT90_M113_HUB_ROSTER_OPS_PROOF"] = str(proof_path)

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

    def test_verifier_rejects_generated_proof_package_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m113-package-proof-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            payload = json.loads(
                (REPO_ROOT / ".codex-studio" / "published" / "NEXT90_M113_HUB_ROSTER_OPS.generated.json").read_text(
                    encoding="utf-8"
                )
            )
            payload["package_proof"] = {
                **payload["package_proof"],
                "package_id": "next90-m112-hub-campaign-consequence-truth",
                "milestone_id": 112,
                "frontier_id": 4730880976,
                "owned_surfaces": ["campaign_memory:consequence_truth", "downtime_aftermath:api"],
            }
            proof_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_NEXT90_M113_HUB_ROSTER_OPS_PROOF"] = str(proof_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package_proof drifted", result.stderr)

    @staticmethod
    def copy_sources(temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def run_verifier(self, temp_root: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_NEXT90_M113_HUB_ROSTER_OPS_ROOT"] = str(temp_root)
        env["CHUMMER_NEXT90_M113_HUB_ROSTER_OPS_PROOF"] = str(temp_root / ".codex-studio/published/NEXT90_M113_HUB_ROSTER_OPS.generated.json")
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_next90_m113_hub_roster_ops.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
