from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m144_hub_release_truth_alignment.py"
SOURCE_FILES = [
    "Chummer.Run.Api/Services/PublicReleaseManifestService.cs",
    "Chummer.Run.Api/Services/SignedInTrustStatusService.cs",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/ai/verify.sh",
    ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json",
    "Chummer.Portal/downloads/startup-smoke/startup-smoke-avalonia-osx-arm64.receipt.json",
    "Chummer.Portal/downloads/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json",
]


class Next90M144HubReleaseTruthAlignmentTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_release_truth_alignment(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m144 hub release truth alignment proof passed", result.stdout)

    def test_verify_script_runs_m144_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/verify_next90_m144_hub_release_truth_alignment.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m144_hub_release_truth_alignment.py", verify_script)

    def test_verifier_fails_when_identity_registry_route_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m144-route-drift-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            release_channel_path = temp_root / "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"
            payload = json.loads(release_channel_path.read_text(encoding="utf-8"))
            payload["artifactIdentityRegistry"][0]["publicInstallRoute"] = "/downloads/install/drifted-route"
            release_channel_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("artifactIdentityRegistry tuple avalonia:linux:linux-x64 drifted", result.stderr)

    def test_verifier_fails_when_install_recovery_refs_drop_tuple_marker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m144-proof-ref-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            release_channel_path = temp_root / "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"
            payload = json.loads(release_channel_path.read_text(encoding="utf-8"))
            payload["installAwareArtifactRegistry"][0]["recoveryProofRefs"] = [
                "/downloads/install/avalonia-win-x64-installer"
            ]
            release_channel_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("recoveryProofRefs missing desktopTupleCoverage.desktopRouteTruth[avalonia:linux:linux-x64]", result.stderr)

    def test_verifier_fails_when_release_proof_route_drops_promoted_install_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m144-proof-route-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            payload = json.loads(proof_path.read_text(encoding="utf-8"))
            payload["proof_routes"] = [
                route
                for route in payload["proof_routes"]
                if route != "/downloads/install/avalonia-win-x64-installer"
            ]
            proof_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("proof_routes missing required route /downloads/install/avalonia-win-x64-installer", result.stderr)

    def test_verifier_fails_when_stale_startup_smoke_is_not_reflected_in_release_truth(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m144-startup-smoke-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            release_channel_path = temp_root / "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"
            payload = json.loads(release_channel_path.read_text(encoding="utf-8"))
            for tuple_truth in payload["desktopTupleCoverage"]["desktopRouteTruth"]:
                if tuple_truth.get("tupleId") == "avalonia:windows:win-x64":
                    tuple_truth["artifactId"] = "avalonia-win-x64-archive"
                    break
            payload["supportabilityState"] = "published"
            payload["rolloutState"] = "published"
            payload["message"] = "Shelf is fully live."
            release_channel_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            startup_smoke_path = temp_root / "Chummer.Portal/downloads/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json"
            startup_smoke_payload = json.loads(startup_smoke_path.read_text(encoding="utf-8"))
            startup_smoke_payload["artifactSha256"] = "deadbeef" * 8
            startup_smoke_path.write_text(json.dumps(startup_smoke_payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must stay review_required", result.stderr)
        self.assertIn("must stay coverage_incomplete", result.stderr)

    def copy_sources(self, temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def run_verifier(self, temp_root: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_NEXT90_M144_ROOT"] = str(temp_root)
        env["CHUMMER_NEXT90_M144_LOCAL_RELEASE_PROOF"] = str(
            temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
        )
        env["CHUMMER_NEXT90_M144_SERVED_RELEASE_PROOF"] = str(
            temp_root / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
        )
        env["CHUMMER_NEXT90_M144_RELEASE_CHANNEL"] = str(
            temp_root / "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"
        )
        env["CHUMMER_NEXT90_M144_STARTUP_SMOKE_ROOT"] = str(
            temp_root / "Chummer.Portal/downloads/startup-smoke"
        )
        return subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
