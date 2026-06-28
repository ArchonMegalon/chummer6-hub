from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = REPO_ROOT / "scripts" / "materialize_hub_local_release_proof.py"


class HubLocalReleaseProofMaterializerSyncTests(unittest.TestCase):
    def test_materializer_syncs_fresh_flagship_readiness_into_explicit_mirror_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            proof_path = temp_root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            source_readiness_path = temp_root / "fleet" / "FLAGSHIP_PRODUCT_READINESS.generated.json"
            mirrored_readiness_path = temp_root / "local" / "FLAGSHIP_PRODUCT_READINESS.generated.json"
            source_readiness_path.parent.mkdir(parents=True, exist_ok=True)
            mirrored_readiness_path.parent.mkdir(parents=True, exist_ok=True)

            source_payload = {
                "contract_name": "fleet.flagship_product_readiness",
                "generated_at": "2026-06-27T19:45:08Z",
                "status": "pass",
                "scoped_status": "ready",
                "missing_keys": [],
                "scoped_missing_keys": [],
                "completion_audit": {
                    "status": "pass",
                    "reason": "Flagship product readiness proof is green.",
                },
                "flagship_readiness_audit": {
                    "reason": "Flagship product readiness proof is green.",
                    "missing_coverage_keys": [],
                    "scoped_missing_coverage_keys": [],
                },
            }
            mirrored_stale_payload = {
                "contract_name": "fleet.flagship_product_readiness",
                "generated_at": "2026-06-27T18:54:35Z",
                "status": "fail",
                "scoped_status": "fail",
                "missing_keys": ["desktop_client"],
                "scoped_missing_keys": ["desktop_client"],
                "completion_audit": {
                    "status": "fail",
                    "reason": "stale drift",
                },
                "flagship_readiness_audit": {
                    "reason": "stale drift",
                    "missing_coverage_keys": ["desktop_client"],
                    "scoped_missing_coverage_keys": ["desktop_client"],
                },
            }
            source_readiness_path.write_text(json.dumps(source_payload), encoding="utf-8")
            mirrored_readiness_path.write_text(json.dumps(mirrored_stale_payload), encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH"] = str(source_readiness_path)
            env["CHUMMER_LOCAL_FLAGSHIP_READINESS_SYNC_PATH"] = str(mirrored_readiness_path)

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    str(proof_path),
                    "http://127.0.0.1:8091",
                    "docker-compose.public-edge.yml",
                    "300",
                    "true",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout)

            mirrored_payload = json.loads(mirrored_readiness_path.read_text(encoding="utf-8"))
            self.assertEqual(source_payload, mirrored_payload)


if __name__ == "__main__":
    unittest.main()
