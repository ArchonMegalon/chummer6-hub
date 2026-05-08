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
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m121_hub_runboard_resolution.py"
SOURCE_FILES = [
    "Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs",
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
    "Chummer.Run.Api/Views/Accounts/Account.cshtml",
    "tests/RunServicesSmoke/Program.cs",
    "tests/RunServicesVerification/CampaignSpineRestoreVerification.cs",
    "scripts/materialize_next90_m121_hub_runboard_resolution_proof.py",
    "scripts/verify_next90_m121_hub_runboard_resolution.py",
    "scripts/ai/verify.sh",
    ".codex-design/product/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    ".codex-studio/published/NEXT90_M121_HUB_RUNBOARD_RESOLUTION.generated.json",
]


@unittest.skip("Superseded by the current runboard continuity proof suite.")
class Next90M121HubRunboardResolutionProofTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_runboard_resolution_proof(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m121 hub runboard resolution proof passed", result.stdout)

    def test_verify_script_runs_m121_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/materialize_next90_m121_hub_runboard_resolution_proof.py", verify_script)
        self.assertIn("python3 scripts/verify_next90_m121_hub_runboard_resolution.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m121_hub_runboard_resolution_proof.py", verify_script)

    def test_verifier_fails_when_queue_status_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m121-queue-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            queue_path = temp_root / "fleet-queue.yaml"
            design_queue_path = temp_root / ".codex-design/product/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            shutil.copyfile("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml", queue_path)
            queue_payload = yaml.safe_load(queue_path.read_text(encoding="utf-8"))
            for item in queue_payload["items"]:
                if item.get("package_id") == "next90-m121-hub-persist-session-turn-ledger-handoff-runboard-state-and-r":
                    item["status"] = "complete"
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status must be 'not_started'", result.stderr)

    def test_verifier_fails_when_server_plane_drops_resolution_posture_marker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m121-server-plane-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            service_path = temp_root / "Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs"
            service_text = service_path.read_text(encoding="utf-8")
            service_path.write_text(
                service_text.replace(
                    '? "ResolutionReport draft posture: contested-turn follow-through stays draft-scoped on the shared continuity lane until an approved report supersedes it."',
                    '? "ResolutionReport posture removed."',
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ResolutionReport draft posture", result.stderr)

    def test_verifier_fails_when_account_view_drops_runboard_option(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m121-account-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            account_path = temp_root / "Chummer.Run.Api/Views/Accounts/Account.cshtml"
            account_text = account_path.read_text(encoding="utf-8")
            account_path.write_text(
                account_text.replace('<option value="runboard_state">Runboard state</option>', "", 1),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('<option value="runboard_state">Runboard state</option>', result.stderr)

    def test_verifier_fails_when_smoke_drops_runboard_change_packet_guard(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m121-smoke-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            assertion = 'Assert(refreshedWorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "runboard_state", StringComparison.Ordinal)) == true, "campaign spine server plane api should name runboard packets explicitly on the bounded what-changed rail.");'
            smoke_path.write_text(smoke_text.replace(assertion, "", 1), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('string.Equals(item.Kind, "runboard_state"', result.stderr)

    def test_verifier_rejects_active_run_markers_in_generated_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m121-proof-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            payload = json.loads(
                (REPO_ROOT / ".codex-studio/published/NEXT90_M121_HUB_RUNBOARD_RESOLUTION.generated.json").read_text(
                    encoding="utf-8"
                )
            )
            payload["required_markers"]["persist_session_turn_ledger_handoff:hub"].append(
                "TASK_LOCAL_TELEMETRY.generated.json is forbidden completion proof."
            )
            proof_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_NEXT90_M121_HUB_PROOF"] = str(proof_path)

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
        with tempfile.TemporaryDirectory(prefix="next90-m121-package-proof-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            payload = json.loads(
                (REPO_ROOT / ".codex-studio/published/NEXT90_M121_HUB_RUNBOARD_RESOLUTION.generated.json").read_text(
                    encoding="utf-8"
                )
            )
            payload["package_proof"] = {
                **payload["package_proof"],
                "package_id": "next90-m122-hub-campaign-adoption",
                "milestone_id": 122,
                "frontier_id": 123,
                "owned_surfaces": ["campaign_adoption"],
            }
            proof_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_NEXT90_M121_HUB_PROOF"] = str(proof_path)

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

    def run_verifier(
        self,
        temp_root: Path,
        *,
        queue_path: Path | None = None,
        design_queue_path: Path | None = None,
        successor_registry_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_NEXT90_M121_HUB_ROOT"] = str(temp_root)
        env["CHUMMER_NEXT90_M121_HUB_PROOF"] = str(
            temp_root / ".codex-studio/published/NEXT90_M121_HUB_RUNBOARD_RESOLUTION.generated.json"
        )
        if queue_path is not None:
            env["CHUMMER_NEXT90_M121_HUB_QUEUE_STAGING"] = str(queue_path)
        if design_queue_path is not None:
            env["CHUMMER_NEXT90_M121_HUB_DESIGN_QUEUE_STAGING"] = str(design_queue_path)
        if successor_registry_path is not None:
            env["CHUMMER_NEXT90_M121_HUB_SUCCESSOR_REGISTRY"] = str(successor_registry_path)
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_next90_m121_hub_runboard_resolution.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
