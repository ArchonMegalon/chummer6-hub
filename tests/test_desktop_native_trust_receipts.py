from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_desktop_native_trust_receipts.py"
PROOF_SCRIPT = REPO_ROOT / "scripts" / "materialize_hub_local_release_proof.py"
QUEUE_PROOF_LINES = [
    "    proof:",
    "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InstallLinkingController.cs",
    "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/DesktopInstallRail.cs",
    "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/Support/SupportCasePresentationService.cs",
    "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml",
    "      - /docker/chummercomplete/chummer.run-services/scripts/verify_desktop_native_trust_receipts.py",
    "      - /docker/chummercomplete/chummer.run-services/tests/test_desktop_native_trust_receipts.py",
    "      - /docker/chummercomplete/chummer.run-services/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "      - /docker/chummercomplete/chummer.run-services commit e27f24c1 tightens desktop-native continuation fallback-posture proof.",
    "      - /docker/chummercomplete/chummer.run-services commit e578a519 tightens the completed M102 proof pin.",
    "      - /docker/chummercomplete/chummer.run-services commit 9fcec2a0 fail-closes M102 queue and registry proof when active-run telemetry helper output is cited as package evidence.",
    "      - /docker/chummercomplete/chummer.run-services commit 266d526b pins the M102 queue proof hardening commit.",
    "      - /docker/chummercomplete/chummer.run-services commit 6ea510c8 pins the M102 telemetry guard proof evidence.",
    "      - /docker/chummercomplete/chummer.run-services commit 7a825c73 pins the M102 desktop trust guard evidence.",
    "      - python3 scripts/verify_desktop_native_trust_receipts.py",
    "      - python3 -m unittest tests/test_desktop_native_trust_receipts.py",
    '      - dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "DesktopInstallRailTests|PublicLandingClaimRecoveryFlowTests|InstallLinkingContinuationVerification" --no-restore',
]
REGISTRY_102_1_LINES = [
    "milestones:",
    "  - id: 102",
    "    work_tasks:",
    "      - id: 102.1",
    "        owner: chummer6-hub",
    "        status: complete",
    "        landed_commit: 160af58f",
    "        evidence:",
    "          - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InstallLinkingController.cs exposes /api/v1/install-linking/continuation for grant-bound claimed desktop installs with current release, update, rollback, and support continuation truth.",
    "          - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/PublicLanding/DownloadDispatch.cshtml and /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Views/Accounts/Account.cshtml make guided setup/app continuation the default and keep claim codes as recovery fallback only.",
    "          - /docker/chummercomplete/chummer.run-services/scripts/verify_desktop_native_trust_receipts.py fail-closes missing source markers and missing successor proof receipts for desktop_native_claim_and_recovery and support_followthrough:install_truth.",
    "          - /docker/chummercomplete/chummer.run-services/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json carries next90-m102-hub-desktop-native-trust proof receipts for /downloads/install/avalonia-linux-x64-installer/continue.json, /api/v1/install-linking/continuation, /account/access, /account/support, and /contact.",
    "          - /docker/chummercomplete/chummer.run-services commit e27f24c1 tightens desktop-native continuation fallback-posture proof so claimed installs return the same fallback posture used by download and support recovery.",
    "          - /docker/chummercomplete/chummer.run-services commit e578a519 tightens the completed M102 proof pin so future shards verify the closed package instead of repeating it.",
    "          - /docker/chummercomplete/chummer.run-services commit 9fcec2a0 fail-closes M102 queue and registry proof when active-run telemetry helper output is cited as package evidence.",
    "          - /docker/chummercomplete/chummer.run-services commit 266d526b pins the M102 queue proof hardening commit so stale queue proof cannot keep the package green.",
    "          - /docker/chummercomplete/chummer.run-services commit 6ea510c8 pins the M102 telemetry guard proof evidence so future shards verify the latest closed-package guard.",
    "          - /docker/chummercomplete/chummer.run-services commit 7a825c73 pins the M102 desktop trust guard evidence into the verifier and unit guard.",
    "          - python3 scripts/verify_desktop_native_trust_receipts.py and python3 -m unittest tests/test_desktop_native_trust_receipts.py exit 0.",
    '          - dotnet test Chummer.Tests/Chummer.Tests.csproj --filter "DesktopInstallRailTests|PublicLandingClaimRecoveryFlowTests|InstallLinkingContinuationVerification" --no-restore exits 0 for net10.0 and net10.0-windows.',
]
ABSOLUTE_REPO_PREFIX = "/docker/chummercomplete/chummer.run-services/"


def load_verifier_module():
    spec = importlib.util.spec_from_file_location("verify_desktop_native_trust_receipts", VERIFY_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load verifier module from {VERIFY_SCRIPT}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def proof_anchor_paths() -> list[Path]:
    anchors: list[Path] = []
    for value in [*QUEUE_PROOF_LINES, *REGISTRY_102_1_LINES]:
        stripped = value.strip()
        if not stripped.startswith("- "):
            continue

        proof_value = stripped[2:]
        if not proof_value.startswith(ABSOLUTE_REPO_PREFIX):
            continue

        relative = proof_value[len(ABSOLUTE_REPO_PREFIX) :].split(" ", 1)[0]
        if relative and relative not in {str(item) for item in anchors}:
            anchors.append(Path(relative))

    return anchors


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
            payload = json.loads(proof)
            self.assertIn("/account/access", payload["proof_routes"])
            m102_package = next(
                item
                for item in payload["successor_queue_packages"]
                if item["package_id"] == "next90-m102-hub-desktop-native-trust"
            )
            self.assertEqual("complete", m102_package["status"])
            self.assertEqual("160af58f", m102_package["landed_commit"])
            self.assertEqual(
                "Unify claim, install, update, and support recovery into one desktop-native flow",
                m102_package["title"],
            )
            self.assertEqual(["Chummer.Run.Api", "scripts", "tests"], m102_package["allowed_paths"])
            self.assertEqual(
                "Claim, update, rollback, recovery, and support followthrough happen from the installer or app, not as browser ritual.",
                m102_package["exit_criterion"],
            )
            m105_package = next(
                item
                for item in payload["successor_queue_packages"]
                if item["package_id"] == "next90-m105-hub-workspace-continuity"
            )
            self.assertEqual("complete", m105_package["status"])
            self.assertEqual("4d4b3856", m105_package["landed_commit"])
            self.assertEqual(["Chummer.Run.Api", "scripts", "tests"], m105_package["allowed_paths"])
            self.assertEqual(
                ["workspace_restore:provenance", "entitlement_sync:conflict_receipts"],
                m105_package["owned_surfaces"],
            )

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
                        "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                        "    package_id: next90-m102-hub-desktop-native-trust",
                        "    frontier_id: 2897065929",
                        "    milestone_id: 102",
                        "    wave: W6",
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
                        "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                        "    package_id: next90-m102-hub-desktop-native-trust",
                        "    frontier_id: 2897065929",
                        "    milestone_id: 102",
                        "    wave: W6",
                        "    repo: chummer6-hub",
                        "    status: complete",
                        "    landed_commit: 160af58f",
                        *QUEUE_PROOF_LINES,
                        "    allowed_paths:",
                        "      - Chummer.Run.Api",
                        "      - scripts",
                        "      - tests",
                        "    owned_surfaces:",
                        "      - desktop_native_claim_and_recovery",
                        "      - support_followthrough:install_truth",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
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
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
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
                "\n".join(REGISTRY_102_1_LINES) + "\n",
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

    def test_verifier_fail_closes_successor_queue_package_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(
                complete_queue.replace(
                    "task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "task: Browser-only support fallback.",
                )
                + "\n",
                encoding="utf-8",
            )
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
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
            self.assertIn(
                "canonical successor queue staging block missing marker: "
                "task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                result.stderr,
            )

    def test_verifier_fail_closes_successor_queue_frontier_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(
                complete_queue.replace("    frontier_id: 2897065929\n", "") + "\n",
                encoding="utf-8",
            )
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
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
            self.assertIn("canonical successor queue staging block missing marker: frontier_id: 2897065929", result.stderr)

    def test_verifier_fail_closes_successor_queue_scope_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(
                complete_queue.replace("      - tests\n", "") + "\n",
                encoding="utf-8",
            )
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
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
            self.assertIn("canonical successor queue staging block has wrong allowed_paths", result.stderr)

    def test_verifier_fail_closes_successor_queue_proof_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(
                complete_queue.replace(
                    "      - python3 scripts/verify_desktop_native_trust_receipts.py\n",
                    "",
                )
                + "\n",
                encoding="utf-8",
            )
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
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
            self.assertIn("canonical successor queue staging block has wrong proof", result.stderr)

    def test_verifier_fail_closes_successor_registry_evidence_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(
                    line
                    for line in REGISTRY_102_1_LINES
                    if "python3 scripts/verify_desktop_native_trust_receipts.py and python3 -m unittest" not in line
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
            self.assertIn("canonical successor registry block has wrong evidence", result.stderr)

    def test_verifier_fail_closes_successor_queue_active_run_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(
                complete_queue.replace(
                    "      - python3 -m unittest tests/test_desktop_native_trust_receipts.py\n",
                    "      - python3 -m unittest tests/test_desktop_native_trust_receipts.py\n"
                    "      - /var/lib/codex-fleet/chummer_design_supervisor/shard-1/ACTIVE_RUN_HANDOFF.generated.md\n",
                )
                + "\n",
                encoding="utf-8",
            )
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(REGISTRY_102_1_LINES) + "\n",
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
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: /var/lib/codex-fleet",
                result.stderr,
            )
            self.assertIn(
                "canonical successor queue staging block has forbidden active-run proof marker: ACTIVE_RUN_HANDOFF",
                result.stderr,
            )

    def test_verifier_fail_closes_successor_registry_active_run_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path = Path(temp_root) / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
            registry_path = Path(temp_root) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            complete_queue = "\n".join(
                [
                    "items:",
                    "  - title: Unify claim, install, update, and support recovery into one desktop-native flow",
                    "    task: Remove browser ritual from claim, install, update, rollback, and support continuation for claimed desktop users.",
                    "    package_id: next90-m102-hub-desktop-native-trust",
                    "    frontier_id: 2897065929",
                    "    milestone_id: 102",
                    "    wave: W6",
                    "    repo: chummer6-hub",
                    "    status: complete",
                    "    landed_commit: 160af58f",
                    *QUEUE_PROOF_LINES,
                    "    allowed_paths:",
                    "      - Chummer.Run.Api",
                    "      - scripts",
                    "      - tests",
                    "    owned_surfaces:",
                    "      - desktop_native_claim_and_recovery",
                    "      - support_followthrough:install_truth",
                ]
            )
            queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            design_queue_path.write_text(complete_queue + "\n", encoding="utf-8")
            registry_path.write_text(
                "\n".join(
                    [
                        *REGISTRY_102_1_LINES,
                        "          - TASK_LOCAL_TELEMETRY.generated.json active-run helper output",
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
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: TASK_LOCAL_TELEMETRY",
                result.stderr,
            )
            self.assertIn(
                "canonical successor registry block has forbidden active-run proof marker: active-run helper",
                result.stderr,
            )

    def test_verifier_fail_closes_generated_proof_package_scope_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
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
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            m102_package = next(
                item
                for item in proof["successor_queue_packages"]
                if item["package_id"] == "next90-m102-hub-desktop-native-trust"
            )
            m102_package["allowed_paths"] = ["Chummer.Run.Api", "scripts"]
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("proof package has wrong allowed_paths", result.stderr)
            self.assertIn(
                "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from scripts/materialize_hub_local_release_proof.py",
                result.stderr,
            )

    def test_verifier_fail_closes_materialized_proof_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
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
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            m102_receipt = next(
                item
                for item in proof["proof_receipts"]
                if item["receipt_id"] == "desktop_native_claim_and_recovery"
            )
            m102_receipt["summary"] = "stale local receipt text"
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from scripts/materialize_hub_local_release_proof.py",
                result.stderr,
            )

    def test_verifier_fail_closes_weakened_generated_package_exit_criterion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
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
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            m102_package = next(
                item
                for item in proof["successor_queue_packages"]
                if item["package_id"] == "next90-m102-hub-desktop-native-trust"
            )
            m102_package["exit_criterion"] = "Claim codes are still acceptable as the main continuation path."
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("proof package has wrong exit_criterion", result.stderr)
            self.assertIn(
                "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from scripts/materialize_hub_local_release_proof.py",
                result.stderr,
            )

    def test_verifier_fail_closes_weakened_desktop_native_receipt_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
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
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            m102_receipt = next(
                item
                for item in proof["proof_receipts"]
                if item["receipt_id"] == "desktop_native_claim_and_recovery"
            )
            m102_receipt["summary"] = "Claim continuation may start in a browser if that is more convenient."
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("desktop_native_claim_and_recovery has wrong summary", result.stderr)
            self.assertIn(
                "published HUB_LOCAL_RELEASE_PROOF.generated.json drifts from scripts/materialize_hub_local_release_proof.py",
                result.stderr,
            )

    def test_verifier_fail_closes_missing_canonical_proof_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            anchor_root = Path(temp_root)
            missing_anchor = Path("tests/test_desktop_native_trust_receipts.py")
            for anchor in proof_anchor_paths():
                if anchor == missing_anchor:
                    continue

                path = anchor_root / anchor
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("placeholder\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_RUN_SERVICES_PROOF_ANCHOR_ROOT": str(anchor_root),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "canonical proof anchor does not resolve: "
                "/docker/chummercomplete/chummer.run-services/tests/test_desktop_native_trust_receipts.py",
                result.stderr,
            )

    def test_verifier_fail_closes_non_resolving_proof_commit(self) -> None:
        result = subprocess.run(
            ["python3", str(VERIFY_SCRIPT)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            env={
                **dict(os.environ),
                "CHUMMER_DESKTOP_NATIVE_TRUST_EXTRA_REQUIRED_COMMITS": "0000000000000000000000000000000000000000",
            },
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "required M102 desktop-native trust proof commit does not resolve: "
            "0000000000000000000000000000000000000000",
            result.stderr,
        )

    def test_verifier_requires_desktop_native_hardening_commits(self) -> None:
        verifier = load_verifier_module()

        self.assertEqual(
            [
                "160af58f",
                "e27f24c1",
                "0ea22419",
                "b4d761a2",
                "e75c4a97",
                "e578a519",
                "9fcec2a0",
                "266d526b",
                "6ea510c8",
                "7a825c73",
            ],
            verifier._required_resolving_commits(),
        )

    def test_verifier_fail_closes_missing_standard_verify_wiring(self) -> None:
        verifier = load_verifier_module()

        with tempfile.TemporaryDirectory() as temp_root:
            repo_root = Path(temp_root)
            for relative_path, markers in verifier.REQUIRED_SOURCE_MARKERS.items():
                path = repo_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            verify_sh = repo_root / "scripts/ai/verify.sh"
            verify_sh.write_text("#!/usr/bin/env bash\nset -euo pipefail\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "scripts/ai/verify.sh missing marker: python3 scripts/verify_desktop_native_trust_receipts.py",
                errors,
            )

    def test_verifier_fail_closes_account_continuation_copy_drift(self) -> None:
        verifier = load_verifier_module()

        with tempfile.TemporaryDirectory() as temp_root:
            repo_root = Path(temp_root)
            for relative_path, markers in verifier.REQUIRED_SOURCE_MARKERS.items():
                path = repo_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative_path == Path("Chummer.Run.Api/Views/Accounts/Account.cshtml"):
                    markers = [
                        marker
                        for marker in markers
                        if marker != "instead of starting a fresh browser ritual."
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Run.Api/Views/Accounts/Account.cshtml missing marker: "
                "instead of starting a fresh browser ritual.",
                errors,
            )

    def test_verifier_fail_closes_support_case_install_receipt_drift(self) -> None:
        verifier = load_verifier_module()

        with tempfile.TemporaryDirectory() as temp_root:
            repo_root = Path(temp_root)
            for relative_path, markers in verifier.REQUIRED_SOURCE_MARKERS.items():
                path = repo_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative_path == Path("Chummer.Run.Api/Controllers/InstallLinkingController.cs"):
                    markers = [
                        marker
                        for marker in markers
                        if marker != "InstalledBuildReceiptId: receipt?.ReceiptId"
                    ]
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")

            errors: list[str] = []
            verifier._verify_required_source_markers(errors, repo_root)

            self.assertIn(
                "Chummer.Run.Api/Controllers/InstallLinkingController.cs missing marker: "
                "InstalledBuildReceiptId: receipt?.ReceiptId",
                errors,
            )

    def test_verifier_fail_closes_top_level_m102_proof_route_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
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
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof["proof_routes"] = [
                item
                for item in proof["proof_routes"]
                if item != "/api/v1/install-linking/continuation"
            ]
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("proof_routes missing M102 route: /api/v1/install-linking/continuation", result.stderr)

    def test_verifier_fail_closes_top_level_m102_journey_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            proof_path = Path(temp_root) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            materialize = subprocess.run(
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
                materialize.returncode,
                msg=f"stdout:\n{materialize.stdout}\nstderr:\n{materialize.stderr}",
            )

            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof["journeys_passed"] = [
                item
                for item in proof["journeys_passed"]
                if item != "install_claim_restore_continue"
            ]
            proof_path.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["python3", str(VERIFY_SCRIPT)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **dict(os.environ),
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_PATH": str(proof_path),
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("journeys_passed missing M102 journey: install_claim_restore_continue", result.stderr)


if __name__ == "__main__":
    unittest.main()
