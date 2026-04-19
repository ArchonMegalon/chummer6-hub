from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = REPO_ROOT / "scripts" / "materialize_hub_local_release_proof.py"
NATIVE_SUPPORT_ROUTE = "/api/v1/install-linking/continuation/support"


class HubLocalReleaseProofNativeSupportRouteTests(unittest.TestCase):
    def test_materialized_m102_proof_includes_native_support_route(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            result = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
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

            self.assertEqual(0, result.returncode, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
            proof = json.loads(proof_path.read_text(encoding="utf-8"))

        support_receipts = [
            receipt
            for receipt in proof["proof_receipts"]
            if receipt.get("receipt_id") == "support_followthrough:install_truth"
        ]
        self.assertEqual(1, len(support_receipts))
        self.assertIn(NATIVE_SUPPORT_ROUTE, support_receipts[0]["routes"])


if __name__ == "__main__":
    unittest.main()
