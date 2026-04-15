from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_desktop_native_trust_receipts.py"
PROOF_SCRIPT = REPO_ROOT / "scripts" / "materialize_hub_local_release_proof.py"


class DesktopNativeTrustReceiptTests(unittest.TestCase):
    def test_verifier_passes_current_repo_and_published_proof(self) -> None:
        result = subprocess.run(
            ["python3", str(VERIFY_SCRIPT)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(
            0,
            result.returncode,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        self.assertIn("desktop native trust receipts verified", result.stdout)

    def test_materializer_publishes_m102_desktop_native_trust_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            result = subprocess.run(
                [
                    "python3",
                    str(PROOF_SCRIPT),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                0,
                result.returncode,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            proof = proof_path.read_text(encoding="utf-8")
            self.assertIn("next90-m102-hub-desktop-native-trust", proof)
            self.assertIn("desktop_native_claim_and_recovery", proof)
            self.assertIn("support_followthrough:install_truth", proof)
            self.assertIn("/api/v1/install-linking/continuation", proof)


if __name__ == "__main__":
    unittest.main()
