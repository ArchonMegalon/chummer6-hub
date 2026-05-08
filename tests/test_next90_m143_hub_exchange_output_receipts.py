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
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m143_hub_exchange_output_receipts.py"
PACKAGE_ID = "next90-m143-hub-bind-exchange-and-outward-facing-output-routes-to-visible-receipt-or-bou"
QUEUE_STAGING = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
SUCCESSOR_REGISTRY = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml")
SOURCE_FILES = [
    "Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "Chummer.Run.Api/Controllers/InstallLinkingController.cs",
    "Chummer.Run.Api/Controllers/CampaignSpineController.cs",
    "Chummer.Run.Api/Services/Community/CampaignFederationOrchestrationService.cs",
    "Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/materialize_hub_local_release_proof.py",
    "scripts/verify_next90_m143_hub_exchange_output_receipts.py",
    "scripts/ai/verify.sh",
    ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json",
]


def load_queue_payload(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError:
        payload = load_target_queue_payload(text, path)

    if not isinstance(payload, dict):
        raise TypeError(f"queue payload at {path} is not a YAML mapping")

    return payload


def load_target_queue_payload(text: str, path: Path) -> dict:
    marker = f"package_id: {PACKAGE_ID}"
    package_index = text.find(marker)
    if package_index < 0:
        raise ValueError(f"unable to parse yaml file: {path}")

    start_candidates = [
        text.rfind("\n- title:", 0, package_index),
        text.rfind("\n  - title:", 0, package_index),
    ]
    block_start = max(start_candidates)
    if block_start < 0:
        if text.startswith("- title:") or text.startswith("  - title:"):
            block_start = 0
        else:
            raise ValueError(f"unable to isolate queue block in {path}")
    else:
        block_start += 1

    end_candidates = [
        index
        for index in (
            text.find("\n- title:", package_index),
            text.find("\n  - title:", package_index),
        )
        if index >= 0
    ]
    block_end = min(end_candidates) if end_candidates else len(text)
    payload = yaml.safe_load(text[block_start:block_end].rstrip() + "\n")
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValueError(f"unable to normalize queue staging yaml: {path}")

    return {"items": payload}


class Next90M143HubExchangeOutputReceiptTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_route_receipt_guards(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m143 hub exchange/output receipt proof passed", result.stdout)

    def test_verify_script_runs_m143_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/verify_next90_m143_hub_exchange_output_receipts.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m143_hub_exchange_output_receipts.py", verify_script)

    def test_verifier_accepts_queue_files_with_prefixed_preamble(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m143-queue-preamble-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            queue_path = temp_root / "fleet-queue.yaml"
            preamble = "# worker note\nselected frontier: 4032374688\n"
            queue_path.write_text(preamble + queue_path.read_text(encoding="utf-8"), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path)

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m143 hub exchange/output receipt proof passed", result.stdout)

    def test_verifier_fails_when_queue_owned_surface_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m143-queue-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            queue_path = temp_root / "fleet-queue.yaml"
            payload = load_queue_payload(queue_path)
            for item in payload["items"]:
                if item.get("package_id") == PACKAGE_ID:
                    item["owned_surfaces"] = ["drifted-surface"]
                    break
            queue_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, queue_path=queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("owned_surfaces drifted", result.stderr)

    def test_verifier_fails_when_public_claim_route_attribute_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m143-claim-route-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    '[HttpGet("/downloads/install/{artifactId}/claim.json")]',
                    '[HttpGet("/downloads/install/{artifactId}/claim-route-drifted.json")]',
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PublicLandingController.cs is missing required guard: [HttpGet("/downloads/install/{artifactId}/claim.json")]', result.stderr)

    def test_verifier_fails_when_registry_work_task_title_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m143-registry-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            registry_path = temp_root / "successor-registry.yaml"
            payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
            for milestone in payload["milestones"]:
                if milestone.get("id") != 143:
                    continue
                for task in milestone["work_tasks"]:
                    if str(task.get("id")) == "143.3":
                        task["title"] = "Drifted title"
                        break
                break
            registry_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(temp_root, successor_registry_path=registry_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("title drifted", result.stderr)

    def test_verifier_fails_when_local_release_proof_drops_m143_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m143-local-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            proof_text = proof_path.read_text(encoding="utf-8")
            proof_path.write_text(
                proof_text.replace(
                    '"receipt_id": "bind_exchange_and_outward_facing_output_routes_to_visibl:hub"',
                    '"receipt_id": "bind_exchange_and_outward_facing_output_routes_to_visibl:removed"',
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("proof_receipts must contain exactly one", result.stderr)

    def test_verifier_fails_when_served_release_proof_drifts_from_local(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m143-served-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            served_path = temp_root / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
            payload = json.loads(served_path.read_text(encoding="utf-8"))
            for receipt in payload["proof_receipts"]:
                if (
                    receipt.get("package_id") == "next90-m143-hub-bind-exchange-and-outward-facing-output-routes-to-visible-receipt-or-bou"
                    and receipt.get("receipt_id") == "bind_exchange_and_outward_facing_output_routes_to_visibl:hub"
                ):
                    receipt["summary"] = "drifted"
                    break
            served_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must match the repo-local proof receipt exactly", result.stderr)

    def test_verifier_fails_when_materializer_drops_m143_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m143-materializer-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            materializer_path = temp_root / "scripts/materialize_hub_local_release_proof.py"
            materializer_text = materializer_path.read_text(encoding="utf-8")
            materializer_path.write_text(
                materializer_text.replace(
                    '"receipt_id": "bind_exchange_and_outward_facing_output_routes_to_visibl:hub"',
                    '"receipt_id": "bind_exchange_and_outward_facing_output_routes_to_visibl:removed"',
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("materialize_hub_local_release_proof.py is missing required guard", result.stderr)

    def test_verifier_fails_when_native_review_required_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m143-native-review-required-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/InstallLinkingController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    "readiness?.MissingDesktopClientCoverage == true",
                    "readiness?.MissingDesktopClientCoverage == false",
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("InstallLinkingController.cs is missing required guard", result.stderr)

    def test_verifier_fails_when_native_route_currentness_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m143-native-currentness-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/InstallLinkingController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    "routeLookup.CurrentnessFailureReason",
                    "routeLookup.RouteProofFreshnessRemoved",
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("InstallLinkingController.cs is missing required guard: routeLookup.CurrentnessFailureReason", result.stderr)

    def test_verifier_fails_when_campaign_federation_bounded_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m143-campaign-bounded-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            service_path = temp_root / "Chummer.Run.Api/Services/Community/CampaignFederationOrchestrationService.cs"
            service_text = service_path.read_text(encoding="utf-8")
            service_path.write_text(
                service_text.replace(
                    'string routeState = allSourcePacksPublished ? "queued" : "bounded_failure";',
                    'string routeState = allSourcePacksPublished ? "queued" : "published";',
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CampaignFederationOrchestrationService.cs is missing required guard", result.stderr)

    def test_verifier_fails_when_smoke_drops_campaign_federation_bounded_assertion(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m143-smoke-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            smoke_path.write_text(
                smoke_text.replace(
                    "campaign federation api should surface batch route posture instead of optimistic launch claims when source-pack receipts are not all live.",
                    "campaign federation bounded assertion removed",
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("campaign federation api should surface batch route posture", result.stderr)

    def copy_sources(self, temp_root: Path) -> None:
        for relative in SOURCE_FILES:
            source = REPO_ROOT / relative
            destination = temp_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

        shutil.copyfile(QUEUE_STAGING, temp_root / "fleet-queue.yaml")
        shutil.copyfile(SUCCESSOR_REGISTRY, temp_root / "successor-registry.yaml")

    def run_verifier(
        self,
        temp_root: Path,
        *,
        queue_path: Path | None = None,
        successor_registry_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "CHUMMER_NEXT90_M143_HUB_ROOT": str(temp_root),
                "CHUMMER_NEXT90_M143_HUB_QUEUE_STAGING": str(queue_path or temp_root / "fleet-queue.yaml"),
                "CHUMMER_NEXT90_M143_HUB_SUCCESSOR_REGISTRY": str(successor_registry_path or temp_root / "successor-registry.yaml"),
                "CHUMMER_NEXT90_M143_HUB_LOCAL_RELEASE_PROOF": str(temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"),
                "CHUMMER_NEXT90_M143_HUB_SERVED_RELEASE_PROOF": str(temp_root / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"),
                "CHUMMER_NEXT90_M143_HUB_PUBLIC_LANDING_CONTROLLER": str(temp_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs"),
                "CHUMMER_NEXT90_M143_HUB_INSTALL_LINKING_CONTROLLER": str(temp_root / "Chummer.Run.Api/Controllers/InstallLinkingController.cs"),
                "CHUMMER_NEXT90_M143_HUB_CAMPAIGN_SPINE_CONTROLLER": str(temp_root / "Chummer.Run.Api/Controllers/CampaignSpineController.cs"),
                "CHUMMER_NEXT90_M143_HUB_CAMPAIGN_FEDERATION_SERVICE": str(temp_root / "Chummer.Run.Api/Services/Community/CampaignFederationOrchestrationService.cs"),
                "CHUMMER_NEXT90_M143_HUB_CREATOR_PUBLICATION_VIEW": str(temp_root / "Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml"),
                "CHUMMER_NEXT90_M143_HUB_SMOKE_PROGRAM": str(temp_root / "tests/RunServicesSmoke/Program.cs"),
                "CHUMMER_NEXT90_M143_HUB_PROOF_MATERIALIZER": str(temp_root / "scripts/materialize_hub_local_release_proof.py"),
                "CHUMMER_NEXT90_M143_HUB_VERIFY_SCRIPT": str(temp_root / "scripts/ai/verify.sh"),
            }
        )
        return subprocess.run(
            ["python3", str(temp_root / "scripts/verify_next90_m143_hub_exchange_output_receipts.py")],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
