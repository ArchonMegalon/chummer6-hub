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
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m122_hub_campaign_adoption.py"
MATERIALIZER = REPO_ROOT / "scripts" / "materialize_next90_m122_hub_campaign_adoption_proof.py"
SOURCE_FILES = [
    "Chummer.Run.Api/Contracts/CampaignAdoptionContracts.cs",
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs",
    "Chummer.Run.Api/Services/Community/CommunityStore.cs",
    "Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
    "tests/RunServicesSmoke/Program.cs",
    "tests/RunServicesVerification/CampaignSpineRestoreVerification.cs",
    "scripts/materialize_next90_m122_hub_campaign_adoption_proof.py",
    "scripts/verify_next90_m122_hub_campaign_adoption.py",
    "scripts/ai/verify.sh",
]


class Next90M122HubCampaignAdoptionProofTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_campaign_adoption_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m122-accepts-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            proof_path = self.materialize_proof(temp_root)

            verifier = self.run_verifier(temp_root, proof_path=proof_path)

        self.assertEqual(verifier.returncode, 0, msg=verifier.stderr or verifier.stdout)
        self.assertIn("next90 m122 hub campaign-adoption proof passed", verifier.stdout)

    def test_verify_script_runs_m122_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/materialize_next90_m122_hub_campaign_adoption_proof.py", verify_script)
        self.assertIn("python3 scripts/verify_next90_m122_hub_campaign_adoption.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m122_hub_campaign_adoption_proof.py", verify_script)

    def test_verifier_fails_when_queue_status_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m122-queue-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            proof_path = self.materialize_proof(temp_root)
            queue_path = temp_root / "queue.yaml"
            payload = self.load_queue_payload(Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml"))
            for item in payload["items"]:
                if item.get("package_id") == "next90-m122-hub-implement-campaign-adoption-wizard-state-runner-goal-per":
                    item["status"] = "in_progress"
                    break
            queue_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, proof_path=proof_path, queue_path=queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status must be 'not_started'", result.stderr)

    def test_verifier_fails_when_service_loses_world_tick_change_packet(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m122-service-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            service_path = temp_root / "Chummer.Run.Api/Services/Community/CampaignSpineService.cs"
            service_text = service_path.read_text(encoding="utf-8")
            service_path.write_text(service_text.replace('Kind: "world_tick",', 'Kind: "world_memory",', 1), encoding="utf-8")
            proof_path = self.materialize_proof(temp_root)

            result = self.run_verifier(temp_root, proof_path=proof_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Kind: "world_tick",', result.stderr)

    def test_verifier_fails_when_generated_proof_package_identity_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m122-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            proof_path = self.materialize_proof(temp_root)
            payload = json.loads(proof_path.read_text(encoding="utf-8"))
            payload["package_proof"] = {**payload["package_proof"], "package_id": "next90-m123-hub-open-runs"}
            proof_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            result = self.run_verifier(temp_root, proof_path=proof_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package_proof drifted", result.stderr)

    def test_verifier_fails_when_smoke_loses_news_item_assertion(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m122-smoke-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            assertion = 'Assert(refreshedWorkspaceServerPlanePayload?.ChangePackets.Any(item => string.Equals(item.Kind, "news_item", StringComparison.Ordinal)) == true, "campaign spine server plane api should add player-safe news items into the bounded what-changed packet rail.");'
            smoke_path.write_text(smoke_text.replace(assertion, "", 1), encoding="utf-8")
            proof_path = self.materialize_proof(temp_root)

            result = self.run_verifier(temp_root, proof_path=proof_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('string.Equals(item.Kind, "news_item"', result.stderr)

    def copy_sources(self, temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def materialize_proof(self, temp_root: Path) -> Path:
        proof_path = temp_root / ".codex-studio/published/NEXT90_M122_HUB_CAMPAIGN_ADOPTION.generated.json"
        proof_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["python3", str(temp_root / "scripts/materialize_next90_m122_hub_campaign_adoption_proof.py")],
            cwd=temp_root,
            env={**os.environ, "CHUMMER_NEXT90_M122_HUB_ROOT": str(temp_root), "CHUMMER_NEXT90_M122_HUB_PROOF_OUT": str(proof_path)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        return proof_path

    def run_verifier(
        self,
        temp_root: Path,
        *,
        proof_path: Path,
        queue_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_NEXT90_M122_HUB_ROOT"] = str(temp_root)
        env["CHUMMER_NEXT90_M122_HUB_PROOF"] = str(proof_path)
        if queue_path is not None:
            env["CHUMMER_NEXT90_M122_HUB_QUEUE_STAGING"] = str(queue_path)
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_next90_m122_hub_campaign_adoption.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def load_queue_payload(self, path: Path) -> dict[str, object]:
        text = path.read_text(encoding="utf-8")
        try:
            payload = yaml.safe_load(text)
        except yaml.YAMLError:
            mode_index = text.find("\nmode:")
            self.assertGreaterEqual(mode_index, 0, "expected queue staging file to expose a mode block")
            prelude = yaml.safe_load(text[:mode_index].strip()) or []
            payload = yaml.safe_load(text[mode_index + 1 :].strip()) or {}
            self.assertIsInstance(prelude, list)
            self.assertIsInstance(payload, dict)
            payload["items"] = [*prelude, *(payload.get("items") or [])]

        self.assertIsInstance(payload, dict)
        return payload


if __name__ == "__main__":
    unittest.main()
