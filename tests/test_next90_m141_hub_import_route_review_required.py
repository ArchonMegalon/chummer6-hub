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
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m141_hub_import_route_review_required.py"
FLEET_QUEUE_STAGING = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
DESIGN_QUEUE_STAGING = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
SUCCESSOR_REGISTRY = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml")
SOURCE_FILES = [
    "Chummer.Run.Api/Services/ImportRouteParityProofGuardService.cs",
    "Chummer.Run.Api/Services/PublicTrustPulseService.cs",
    "Chummer.Run.Api/Services/PublicReleaseManifestService.cs",
    "Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs",
    "Chummer.Run.Api/Controllers/DownloadsCompatibilityController.cs",
    "Chummer.Run.Api/Services/SignedInTrustStatusService.cs",
    "Chummer.Run.Api/ViewModels/SiteViewModels.cs",
    "Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml",
    "Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml",
    "scripts/materialize_hub_local_release_proof.py",
    "scripts/verify_next90_m141_hub_import_route_review_required.py",
    "tests/test_next90_m141_hub_import_route_review_required.py",
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
        payload = yaml.safe_load(normalized_text)

    if not isinstance(payload, dict):
        raise TypeError(f"queue payload at {path} is not a YAML mapping")

    return payload


class Next90M141HubImportRouteReviewRequiredTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_m141_guard(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m141 hub import-route review-required proof passed", result.stdout)

    def test_verify_script_runs_m141_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/verify_next90_m141_hub_import_route_review_required.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m141_hub_import_route_review_required.py", verify_script)

    def test_verifier_fails_when_queue_status_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m141-queue-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            queue_path = temp_root / "fleet-queue.yaml"
            design_queue_path = temp_root / "design-queue.yaml"
            shutil.copyfile(FLEET_QUEUE_STAGING, queue_path)
            shutil.copyfile(DESIGN_QUEUE_STAGING, design_queue_path)
            queue_payload = load_queue_payload(queue_path)
            for item in queue_payload["items"]:
                if item.get("package_id") == "next90-m141-hub-keep-route-support-and-publication-surfaces-from-claiming-parity-for-the":
                    item["status"] = "in_progress"
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status must be 'complete'", result.stderr)

    def test_verifier_fails_when_registry_status_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m141-registry-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            registry_path = temp_root / "successor-registry.yaml"
            shutil.copyfile(SUCCESSOR_REGISTRY, registry_path)
            registry_payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
            for milestone in registry_payload["milestones"]:
                if milestone.get("id") != 141:
                    continue
                for task in milestone["work_tasks"]:
                    if str(task.get("id")) == "141.3":
                        task["status"] = "in_progress"
                        break
                break
            registry_path.write_text(yaml.safe_dump(registry_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, successor_registry_path=registry_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("work task 141.3 status must be 'complete'", result.stderr)

    def test_verifier_fails_when_release_proof_drops_package_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m141-proof-receipt-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            proof_payload = json.loads(proof_path.read_text(encoding="utf-8"))
            proof_payload["proof_receipts"] = [
                receipt
                for receipt in proof_payload["proof_receipts"]
                if receipt.get("receipt_id") != "keep_route_support_and_publication_surfaces_from_claimin:hub"
            ]
            proof_path.write_text(json.dumps(proof_payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "receipt id keep_route_support_and_publication_surfaces_from_claimin:hub must appear exactly once in proof_receipts",
            result.stderr,
        )

    def test_verifier_fails_when_release_proof_drops_package_row(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m141-proof-package-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            proof_payload = json.loads(proof_path.read_text(encoding="utf-8"))
            proof_payload["successor_queue_packages"] = [
                package
                for package in proof_payload["successor_queue_packages"]
                if package.get("package_id") != "next90-m141-hub-keep-route-support-and-publication-surfaces-from-claiming-parity-for-the"
            ]
            proof_payload["successor_queue_packages_by_id"].pop(
                "next90-m141-hub-keep-route-support-and-publication-surfaces-from-claiming-parity-for-the",
                None,
            )
            proof_path.write_text(json.dumps(proof_payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "successor_queue_packages must contain exactly one next90-m141-hub-keep-route-support-and-publication-surfaces-from-claiming-parity-for-the row",
            result.stderr,
        )

    def test_verifier_fails_when_publication_detail_uses_desktop_only_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m141-publication-detail-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            publication_path = temp_root / "Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml"
            publication_path.write_text(
                publication_path.read_text(encoding="utf-8").replace(
                    "Model.TrustPulse?.ParityClaimsReviewRequired == true",
                    "Model.TrustPulse?.MissingDesktopClientCoverage == true",
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Model.TrustPulse?.ParityClaimsReviewRequired == true", result.stderr)

    def copy_sources(self, temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            destination = temp_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text((REPO_ROOT / relative_path).read_text(encoding="utf-8"), encoding="utf-8")

    def run_verifier(
        self,
        temp_root: Path,
        *,
        queue_path: Path | None = None,
        design_queue_path: Path | None = None,
        successor_registry_path: Path | None = None,
        local_release_proof_path: Path | None = None,
        served_release_proof_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_NEXT90_M141_ROOT"] = str(temp_root)
        env["CHUMMER_NEXT90_M141_QUEUE_STAGING"] = str(queue_path or FLEET_QUEUE_STAGING)
        env["CHUMMER_NEXT90_M141_DESIGN_QUEUE_STAGING"] = str(design_queue_path or DESIGN_QUEUE_STAGING)
        env["CHUMMER_NEXT90_M141_SUCCESSOR_REGISTRY"] = str(successor_registry_path or SUCCESSOR_REGISTRY)
        env["CHUMMER_NEXT90_M141_LOCAL_RELEASE_PROOF"] = str(
            local_release_proof_path or temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
        )
        env["CHUMMER_NEXT90_M141_SERVED_RELEASE_PROOF"] = str(
            served_release_proof_path
            or temp_root / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
        )
        return subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
