from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m120_hub_public_launch_health.py"
FLEET_QUEUE_STAGING = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
DESIGN_QUEUE_STAGING = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
SUCCESSOR_REGISTRY = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml")
SOURCE_FILES = [
    "Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "Chummer.Run.Api/Controllers/PublicProgressController.cs",
    "Chummer.Run.Api/ViewModels/SiteViewModels.cs",
    "Chummer.Run.Api/Views/PublicLanding/Status.cshtml",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/materialize_hub_local_release_proof.py",
    "scripts/verify_next90_m120_hub_public_launch_health.py",
    "tests/test_hub_local_release_proof_native_support_route.py",
    "scripts/ai/verify.sh",
    ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json",
]


def load_queue_payload(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        mode_index = text.find("\nmode:")
        if mode_index < 0 and not text.startswith("mode:"):
            raise
        normalized_text = text if text.startswith("mode:") else text[mode_index + 1 :]
        sanitized_lines: list[str] = []
        previous_sequence_indent: int | None = None
        for line in normalized_text.splitlines():
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if (
                sanitized_lines
                and previous_sequence_indent is not None
                and stripped
                and not stripped.startswith("- ")
                and ":" not in stripped
                and indent == previous_sequence_indent
            ):
                sanitized_lines[-1] = f"{sanitized_lines[-1]} {stripped}"
                continue

            sanitized_lines.append(line)
            previous_sequence_indent = indent if stripped.startswith("- ") else None

        payload = yaml.safe_load("\n".join(sanitized_lines) + "\n")

    if not isinstance(payload, dict):
        raise TypeError(f"queue payload at {path} is not a YAML mapping")

    return payload


class Next90M120HubPublicLaunchHealthTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_public_launch_health(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m120 hub public launch health proof passed", result.stdout)

    def test_verify_script_runs_m120_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/verify_next90_m120_hub_public_launch_health.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m120_hub_public_launch_health.py", verify_script)

    def test_verifier_fails_when_queue_status_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m120-queue-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            queue_path = temp_root / "fleet-queue.yaml"
            design_queue_path = temp_root / "design-queue.yaml"
            shutil.copyfile(
                "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
                queue_path,
            )
            shutil.copyfile(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
                design_queue_path,
            )
            queue_payload = load_queue_payload(queue_path)
            for item in queue_payload["items"]:
                if item.get("package_id") == "next90-m120-hub-public-launch-health":
                    item["status"] = "in_progress"
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status must be 'complete'", result.stderr)

    def test_verifier_accepts_queue_files_with_prefixed_preamble_before_mode_block(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m120-queue-preamble-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            queue_path = temp_root / "fleet-queue.yaml"
            design_queue_path = temp_root / "design-queue.yaml"
            preamble = "# worker note\nselected frontier: 4442751895\n"

            queue_path.write_text(
                preamble + queue_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            design_queue_path.write_text(
                preamble + design_queue_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m120 hub public launch health proof passed", result.stdout)

    def test_verifier_fails_when_registry_work_task_title_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m120-registry-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            registry_path = temp_root / "successor-registry.yaml"
            shutil.copyfile(
                "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
                registry_path,
            )
            registry_payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
            for milestone in registry_payload["milestones"]:
                if milestone.get("id") != 120:
                    continue
                for task in milestone["work_tasks"]:
                    if str(task.get("id")) == "120.1":
                        task["title"] = "Drifted title"
                        break
                break
            registry_path.write_text(yaml.safe_dump(registry_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, successor_registry_path=registry_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("work task 120.1 title drifted", result.stderr)

    def test_verifier_fails_when_status_view_loses_launch_health_rows(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m120-status-view-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            status_path = temp_root / "Chummer.Run.Api/Views/PublicLanding/Status.cshtml"
            status_text = status_path.read_text(encoding="utf-8")
            status_path.write_text(
                status_text
                .replace("Model.LaunchHealthRows", "Model.TrustPulse.Rows", 1)
                .replace("Quick release checks", "Quick release summary", 1),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Quick release checks", result.stderr)

    def test_verifier_fails_when_release_proof_drops_public_trust_surface_block(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m120-proof-surface-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            proof_text = proof_path.read_text(encoding="utf-8")
            proof_path.write_text(
                proof_text.replace('"publicTrustSurface"', '"publicTrustSurfaceRemoved"', 1),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing publicTrustSurface block", result.stderr)

    def test_verifier_fails_when_release_proof_drops_launch_health_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m120-proof-receipt-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            proof_text = proof_path.read_text(encoding="utf-8")
            proof_path.write_text(
                proof_text.replace('"receipt_id": "launch_health:public"', '"receipt_id": "launch_health:removed"', 1),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("receipt id launch_health:public must appear exactly once in proof_receipts", result.stderr)

    def test_verifier_fails_when_controller_loses_revoked_launch_health_row(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m120-revoked-row-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace('new("Revoked", BuildRevokedLaunchSummary(manifest)),', 'new("Recalled", BuildRevokedLaunchSummary(manifest)),', 1),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('new("Revoked", BuildRevokedLaunchSummary(manifest)),', result.stderr)

    def test_verifier_fails_when_smoke_drops_fixed_launch_health_assertion(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m120-fixed-row-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            fixed_assertion = 'Assert(statusModel?.LaunchHealthRows?.Any(static row => string.Equals(row.Label, "Fixed", StringComparison.Ordinal) && row.Value.Contains("fix", StringComparison.OrdinalIgnoreCase)) == true, "status page should surface fixed-release follow-through in launch-health rows.");'
            smoke_path.write_text(
                smoke_text.replace(fixed_assertion, "// fixed launch-health assertion removed", 1),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixed-release follow-through", result.stderr)

    def test_verifier_fails_when_release_proof_duplicates_package_receipt_id(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m120-proof-duplicate-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            proof_payload = yaml.safe_load(proof_path.read_text(encoding="utf-8"))
            duplicated_receipt = next(
                receipt
                for receipt in proof_payload["proof_receipts"]
                if receipt.get("package_id") == "next90-m120-hub-public-launch-health"
                and receipt.get("receipt_id") == "launch_health:public"
            )
            proof_payload["proof_receipts"].append(dict(duplicated_receipt))
            proof_path.write_text(json.dumps(proof_payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must not contain duplicate receipt ids: launch_health:public", result.stderr)

    def test_verifier_fails_when_release_proof_duplicates_package_row_in_list(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m120-proof-package-list-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            proof_payload = json.loads(proof_path.read_text(encoding="utf-8"))
            duplicated_package = dict(proof_payload["successor_queue_packages_by_id"]["next90-m120-hub-public-launch-health"])
            proof_payload["successor_queue_packages"].append(duplicated_package)
            proof_path.write_text(json.dumps(proof_payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("successor_queue_packages must contain exactly one next90-m120-hub-public-launch-health row", result.stderr)

    def test_verifier_fails_when_release_proof_reuses_receipt_id_from_another_package(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m120-proof-global-receipt-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            proof_payload = json.loads(proof_path.read_text(encoding="utf-8"))
            proof_payload["proof_receipts"].append(
                {
                    "receipt_id": "launch_health:public",
                    "package_id": "next90-m119-hub-first-session-onboarding",
                    "milestone_id": 119,
                    "frontier_id": 1130567614,
                    "summary": "Conflicting duplicate receipt id.",
                    "routes": ["/home/work"],
                    "surfaces": ["starter_lane:hub"],
                    "evidence": ["conflicting duplicate receipt id"],
                }
            )
            proof_path.write_text(json.dumps(proof_payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("receipt id launch_health:public must appear exactly once in proof_receipts", result.stderr)

    @staticmethod
    def copy_sources(temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        shutil.copyfile(FLEET_QUEUE_STAGING, temp_root / "fleet-queue.yaml")
        shutil.copyfile(DESIGN_QUEUE_STAGING, temp_root / "design-queue.yaml")
        shutil.copyfile(SUCCESSOR_REGISTRY, temp_root / "successor-registry.yaml")

    def run_verifier(
        self,
        temp_root: Path,
        *,
        queue_path: Path | None = None,
        design_queue_path: Path | None = None,
        successor_registry_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_NEXT90_M120_ROOT"] = str(temp_root)
        env["CHUMMER_NEXT90_M120_QUEUE_STAGING"] = str(queue_path or (temp_root / "fleet-queue.yaml"))
        env["CHUMMER_NEXT90_M120_DESIGN_QUEUE_STAGING"] = str(design_queue_path or (temp_root / "design-queue.yaml"))
        env["CHUMMER_NEXT90_M120_SUCCESSOR_REGISTRY"] = str(successor_registry_path or (temp_root / "successor-registry.yaml"))
        env["CHUMMER_NEXT90_M120_LOCAL_RELEASE_PROOF"] = str(temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json")
        env["CHUMMER_NEXT90_M120_SERVED_RELEASE_PROOF"] = str(temp_root / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json")
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_next90_m120_hub_public_launch_health.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
