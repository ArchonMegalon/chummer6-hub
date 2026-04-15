from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_artifact_factory_orchestration.py"
SOURCE_FILES = [
    "Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
    "Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
    "Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
]


class ArtifactFactoryOrchestrationProofTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_artifact_factory_closeout(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("artifact factory orchestration proof passed", result.stdout)

    def test_verifier_fails_closed_when_release_bundle_binding_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            for relative_path in SOURCE_FILES:
                source = REPO_ROOT / relative_path
                target = temp_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

            service_path = temp_root / "Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs"
            service_text = service_path.read_text(encoding="utf-8")
            service_path.write_text(
                service_text.replace(
                    'return $"/artifacts/release-bundles/{Uri.EscapeDataString(anchor.ReleaseArtifactId)}";',
                    'return $"/downloads/install/{Uri.EscapeDataString(anchor.ReleaseArtifactId)}";',
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_ARTIFACT_FACTORY_ROOT"] = str(temp_root)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/artifacts/release-bundles/", result.stderr)

    def test_verifier_fails_closed_when_recipe_specific_shelf_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-shelf-route-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            for relative_path in SOURCE_FILES:
                source = REPO_ROOT / relative_path
                target = temp_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

            service_path = temp_root / "Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs"
            service_text = service_path.read_text(encoding="utf-8")
            service_path.write_text(
                service_text.replace(
                    '            RejectPublicShelfRefOutsideRecipeRoutes(sourcePack.SourcePackId, family, sourcePack.PublicShelfRef, "publicShelfRef");\n',
                    "",
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_ARTIFACT_FACTORY_ROOT"] = str(temp_root)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RejectPublicShelfRefOutsideRecipeRoutes", result.stderr)

    def test_verifier_fails_closed_when_orchestration_service_is_not_registered(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-wiring-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            for relative_path in SOURCE_FILES:
                source = REPO_ROOT / relative_path
                target = temp_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

            service_collection_path = temp_root / "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs"
            service_collection_text = service_collection_path.read_text(encoding="utf-8")
            service_collection_path.write_text(
                service_collection_text.replace(
                    "        services.AddSingleton<ArtifactFactoryOrchestrationService>();\n",
                    "",
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_ARTIFACT_FACTORY_ROOT"] = str(temp_root)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AddSingleton<ArtifactFactoryOrchestrationService>", result.stderr)

    def test_verifier_fails_closed_when_successor_registry_drops_closeout_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-registry-proof-") as temp_dir:
            registry_path = Path(temp_dir) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            registry_path.write_text(
                "\n".join(
                    [
                        "program_wave: next_90_day_product_advance",
                        "milestones:",
                        "  - id: 107",
                        "    title: Artifact factory and public proof shelf",
                        "    work_tasks:",
                        "      - id: 107.1",
                        "        owner: chummer6-hub",
                    ]
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_ARTIFACT_FACTORY_SUCCESSOR_REGISTRY"] = str(registry_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Orchestrate recipe-backed artifact jobs", result.stderr)

    def test_verifier_fails_closed_when_queue_package_allows_extra_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-queue-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            queue_path.write_text(
                "\n".join(
                    [
                        "items:",
                        "  - title: Stand up artifact-factory orchestration for release, support, and publication bundles",
                        "    task: Launch recipe-backed release, fix, support, and publication artifact jobs from approved source packs instead of one-off provider flows.",
                        "    package_id: next90-m107-hub-artifact-factory",
                        "    milestone_id: 107",
                        "    repo: chummer6-hub",
                        "    status: complete",
                        "    landed_commit: b9e6b52e",
                        "    proof:",
                        "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer.run-services/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer.run-services/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer.run-services/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer.run-services/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer.run-services/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer.run-services commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer.run-services commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "    allowed_paths:",
                        "      - Chummer.Run.Api",
                        "      - scripts",
                        "      - tests",
                        "      - Chummer.Run.AI",
                        "    owned_surfaces:",
                        "      - artifact_factory:orchestration",
                        "      - public_proof_shelf:release_bundles",
                    ]
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_ARTIFACT_FACTORY_QUEUE_STAGING"] = str(queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("allowed_paths", result.stderr)
        self.assertIn("unexpected Chummer.Run.AI", result.stderr)

    def test_verifier_fails_closed_when_queue_proof_anchor_does_not_resolve(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-proof-anchor-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            queue_path.write_text(
                "\n".join(
                    [
                        "items:",
                        "  - title: Stand up artifact-factory orchestration for release, support, and publication bundles",
                        "    task: Launch recipe-backed release, fix, support, and publication artifact jobs from approved source packs instead of one-off provider flows.",
                        "    package_id: next90-m107-hub-artifact-factory",
                        "    milestone_id: 107",
                        "    repo: chummer6-hub",
                        "    status: complete",
                        "    landed_commit: b9e6b52e",
                        "    proof:",
                        "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer.run-services/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer.run-services/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer.run-services/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer.run-services/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer.run-services/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer.run-services commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer.run-services commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/MissingArtifactFactoryProofAnchor.cs",
                        "    allowed_paths:",
                        "      - Chummer.Run.Api",
                        "      - scripts",
                        "      - tests",
                        "    owned_surfaces:",
                        "      - artifact_factory:orchestration",
                        "      - public_proof_shelf:release_bundles",
                    ]
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_ARTIFACT_FACTORY_QUEUE_STAGING"] = str(queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("proof anchor does not resolve", result.stderr)
        self.assertIn("MissingArtifactFactoryProofAnchor.cs", result.stderr)


if __name__ == "__main__":
    unittest.main()
