from __future__ import annotations

import os
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

    def test_verifier_fail_closes_successor_queue_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            queue_path.write_text(
                "\n".join(
                    [
                        "items:",
                        "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                        "    package_id: next90-m102-hub-desktop-native-trust",
                        "    milestone_id: 102",
                        "    repo: chummer6-hub",
                        "    status: in_progress",
                        "    allowed_paths:",
                        "      - Chummer.Run.Api",
                        "    owned_surfaces:",
                        "      - desktop_native_claim_and_recovery",
                        "      - support_followthrough:install_truth",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            design_queue_path.write_text(
                "\n".join(
                    [
                        "items:",
                        "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                        "    package_id: next90-m102-hub-desktop-native-trust",
                        "    milestone_id: 102",
                        "    repo: chummer6-hub",
                        "    status: complete",
                        "    landed_commit: 160af58f",
                        "    allowed_paths:",
                        "      - Chummer.Run.Api",
                        "    owned_surfaces:",
                        "      - desktop_native_claim_and_recovery",
                        "      - support_followthrough:install_truth",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            registry_path.write_text(
                "\n".join(
                    [
                        "milestones:",
                        "  - id: 102",
                        "    work_tasks:",
                        "      - id: 102.1",
                        "        owner: chummer6-hub",
                        "        status: complete",
                        "        landed_commit: 160af58f",
                        "        evidence:",
                        "          - next90-m102-hub-desktop-native-trust desktop_native_claim_and_recovery support_followthrough:install_truth",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("canonical successor queue staging block missing marker: status: complete", result.stderr)
            self.assertIn("canonical successor queue staging block missing marker: landed_commit: 160af58f", result.stderr)

    def test_verifier_fail_closes_design_successor_queue_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    milestone_id: 102",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            design_queue_path.write_text(
                complete_queue.replace("landed_commit: 160af58f", "landed_commit: stale-commit") + "\n",
                encoding="utf-8",
            )
            registry_path.write_text(
                "\n".join(
                    [
                        "milestones:",
                        "  - id: 102",
                        "    work_tasks:",
                        "      - id: 102.1",
                        "        owner: chummer6-hub",
                        "        status: complete",
                        "        landed_commit: 160af58f",
                        "        evidence:",
                        "          - next90-m102-hub-desktop-native-trust desktop_native_claim_and_recovery support_followthrough:install_truth",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_NEXT90_QUEUE_STAGING_PATH": str(queue_path),
                    "CHUMMER_NEXT90_DESIGN_QUEUE_STAGING_PATH": str(design_queue_path),
                    "CHUMMER_NEXT90_PRODUCT_ADVANCE_REGISTRY_PATH": str(registry_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("canonical design successor queue staging block missing marker: landed_commit: 160af58f", result.stderr)


if __name__ == "__main__":
    unittest.main()
