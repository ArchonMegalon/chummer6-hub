from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m125_hub_public_signal_packets.py"
SOURCE_FILES = [
    "Chummer.Run.Api/Contracts/SignalToCanonPacketContracts.cs",
    "Chummer.Run.Api/Services/Support/PublicSignalToCanonPacketService.cs",
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
    "Chummer.Tests/PublicSignalToCanonPacketServiceTests.cs",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/materialize_next90_m125_hub_public_signal_packets_proof.py",
    "scripts/verify_next90_m125_hub_public_signal_packets.py",
    "scripts/ai/verify.sh",
]


class Next90M125HubPublicSignalPacketsTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_public_signal_packet_lane(self) -> None:
        result = subprocess.run(["python3", str(SCRIPT)], cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m125 hub public signal packets proof passed", result.stdout)

    def test_verify_script_runs_m125_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/materialize_next90_m125_hub_public_signal_packets_proof.py", verify_script)
        self.assertIn("python3 scripts/verify_next90_m125_hub_public_signal_packets.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m125_hub_public_signal_packets.py", verify_script)

    def test_verifier_fails_when_queue_row_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m125-queue-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            queue_path = temp_root / "fleet-queue.yaml"
            design_queue_path = temp_root / "design-queue.yaml"
            shutil.copyfile("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml", queue_path)
            shutil.copyfile("/docker/chummercomplete/chummer-design-m114/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml", design_queue_path)
            queue_payload = yaml.safe_load(queue_path.read_text(encoding="utf-8"))
            for item in queue_payload["items"]:
                if item.get("package_id") == "next90-m125-hub-build-public-feedback-roadmap-changelog-support-and-sign":
                    item["frontier_id"] = 0
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")
            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("frontier_id must be 4030850391", result.stderr)

    def test_verifier_fails_when_smoke_loses_signal_intake_assertion(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m125-smoke-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            smoke_path.write_text(smoke_text.replace("governed signal-intake packets for the shared participate surface", "signal-intake drift"), encoding="utf-8")
            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("governed signal-intake packets for the shared participate surface", result.stderr)

    @staticmethod
    def copy_sources(temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def run_verifier(self, temp_root: Path, *, queue_path: Path | None = None, design_queue_path: Path | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_NEXT90_M125_ROOT"] = str(temp_root)
        if queue_path is not None:
            env["CHUMMER_NEXT90_M125_QUEUE_STAGING"] = str(queue_path)
        if design_queue_path is not None:
            env["CHUMMER_NEXT90_M125_DESIGN_QUEUE_STAGING"] = str(design_queue_path)
        return subprocess.run(["python3", str(temp_root / "scripts/verify_next90_m125_hub_public_signal_packets.py")], cwd=temp_root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


if __name__ == "__main__":
    unittest.main()
