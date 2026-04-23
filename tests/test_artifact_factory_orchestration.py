from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_artifact_factory_orchestration.py"
CANONICAL_SUCCESSOR_REGISTRY = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml")
CANONICAL_FLEET_QUEUE = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
SOURCE_FILES = [
    "scripts/verify_artifact_factory_orchestration.py",
    "scripts/ai/verify.sh",
    "scripts/launch_artifact_factory_source_pack_batch.py",
    "Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
    "Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
    "Chummer.Run.Api/Controllers/PublicLandingController.cs",
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
    "Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
    "tests/test_artifact_factory_orchestration.py",
    "tests/test_artifact_factory_source_pack_launcher.py",
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

    def test_verifier_fails_closed_when_batch_launcher_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-batch-proof-") as temp_dir:
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
                    "public ArtifactFactoryJobBatchLaunchResult LaunchJobs(ArtifactFactoryJobBatchLaunchRequest request)",
                    "public ArtifactFactoryJobBatchLaunchResult LaunchJobBatchRemoved(ArtifactFactoryJobBatchLaunchRequest request)",
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
        self.assertIn("LaunchJobs(ArtifactFactoryJobBatchLaunchRequest request)", result.stderr)

    def test_verifier_fails_closed_when_batch_recipe_ids_are_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-batch-recipe-proof-") as temp_dir:
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
                    "    IReadOnlyList<string> RecipeIds,\n",
                    "",
                ).replace(
                    "        string[] recipeIds = jobs\n"
                    "            .Select(static job => job.RecipeId)\n"
                    "            .Distinct(StringComparer.OrdinalIgnoreCase)\n"
                    "            .Order(StringComparer.OrdinalIgnoreCase)\n"
                    "            .ToArray();\n",
                    "",
                ).replace(
                    "            RecipeIds: recipeIds,\n",
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
        self.assertIn("RecipeIds", result.stderr)

    def test_verifier_fails_closed_when_batch_source_pack_ids_are_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-batch-source-pack-proof-") as temp_dir:
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
                    "    IReadOnlyList<string> SourcePackIds,\n",
                    "",
                ).replace(
                    "        string[] sourcePackIds = jobs\n"
                    "            .SelectMany(static job => job.SourcePackIds)\n"
                    "            .Distinct(StringComparer.OrdinalIgnoreCase)\n"
                    "            .Order(StringComparer.OrdinalIgnoreCase)\n"
                    "            .ToArray();\n",
                    "",
                ).replace(
                    "            SourcePackIds: sourcePackIds,\n",
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
        self.assertIn("SourcePackIds", result.stderr)

    def test_verifier_fails_closed_when_batch_endpoint_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-batch-endpoint-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            for relative_path in SOURCE_FILES:
                source = REPO_ROOT / relative_path
                target = temp_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

            controller_path = temp_root / "Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    '[HttpPost("/api/internal/artifact-factory/job-batches")]',
                    '[HttpPost("/api/internal/artifact-factory/batches-removed")]',
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
        self.assertIn("/api/internal/artifact-factory/job-batches", result.stderr)

    def test_verifier_fails_closed_when_source_pack_batch_endpoint_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-source-pack-batch-endpoint-") as temp_dir:
            temp_root = Path(temp_dir)
            for relative_path in SOURCE_FILES:
                source = REPO_ROOT / relative_path
                target = temp_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

            controller_path = temp_root / "Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    '[HttpPost("/api/internal/artifact-factory/source-pack-batches")]',
                    '[HttpPost("/api/internal/artifact-factory/source-pack-batches-removed")]',
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
        self.assertIn("/api/internal/artifact-factory/source-pack-batches", result.stderr)

    def test_verifier_fails_closed_when_source_pack_batch_launcher_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-source-pack-batch-service-") as temp_dir:
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
                    "public ArtifactFactoryJobBatchLaunchResult LaunchSourcePackBatch(ArtifactFactorySourcePackBatchLaunchRequest request)",
                    "public ArtifactFactoryJobBatchLaunchResult LaunchSourcePackBatchRemoved(ArtifactFactorySourcePackBatchLaunchRequest request)",
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
        self.assertIn("LaunchSourcePackBatch(ArtifactFactorySourcePackBatchLaunchRequest request)", result.stderr)

    def test_verifier_fails_closed_when_source_pack_batch_id_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-source-pack-batch-id-") as temp_dir:
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
                    "        if (string.IsNullOrWhiteSpace(request.BatchId))\n"
                    "        {\n"
                    "            throw new InvalidDataException(\"source-pack batchId is required.\");\n"
                    "        }\n\n"
                    "        RejectUnsafeBatchId(request.BatchId);\n\n",
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
        self.assertIn("source-pack batchId is required", result.stderr)

    def test_verifier_fails_closed_when_source_pack_batch_preflight_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-source-pack-batch-proof-") as temp_dir:
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
                    "        ValidateSourcePackBatchSourcePacks(request.SourcePacks);\n\n",
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
        self.assertIn("ValidateSourcePackBatchSourcePacks", result.stderr)

    def test_verifier_fails_closed_when_source_pack_batch_format_scope_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-source-pack-format-scope-") as temp_dir:
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
                    "        RejectRequestedFormatOverridesOutsideRequiredFamilies(request.BatchId, requestedFormatsByFamily, requiredFamilies);\n",
                    "",
                ).replace(
                    "\n    private static void RejectRequestedFormatOverridesOutsideRequiredFamilies(\n"
                    "        string batchId,\n"
                    "        IReadOnlyDictionary<string, IReadOnlyList<string>> requestedFormatsByFamily,\n"
                    "        IReadOnlyList<string> requiredFamilies)\n"
                    "    {\n"
                    "        string[] extraFamilies = requestedFormatsByFamily.Keys\n"
                    "            .Where(family => !requiredFamilies.Contains(family, StringComparer.OrdinalIgnoreCase))\n"
                    "            .Order(StringComparer.OrdinalIgnoreCase)\n"
                    "            .ToArray();\n"
                    "        if (extraFamilies.Length > 0)\n"
                    "        {\n"
                    "            throw new InvalidDataException(\n"
                    "                $\"artifact factory source-pack batch '{batchId.Trim()}' requested formats for family/families not required by the batch: {string.Join(\", \", extraFamilies)}.\");\n"
                    "        }\n"
                    "    }\n",
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
        self.assertIn("RejectRequestedFormatOverridesOutsideRequiredFamilies", result.stderr)

    def test_verifier_fails_closed_when_source_pack_batch_response_contract_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-source-pack-response-contract-") as temp_dir:
            temp_root = Path(temp_dir)
            for relative_path in SOURCE_FILES:
                source = REPO_ROOT / relative_path
                target = temp_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

            launcher_path = temp_root / "scripts/launch_artifact_factory_source_pack_batch.py"
            launcher_text = launcher_path.read_text(encoding="utf-8")
            launcher_path.write_text(
                launcher_text.replace(
                    "        validate_batch_launch_response(response, recipe_catalog, payload)\n",
                    "",
                ).replace(
                    "\n\ndef validate_batch_launch_response(response: Any, recipe_catalog: dict[str, Any]) -> None:\n"
                    "    if not isinstance(response, dict):\n"
                    "        raise LaunchValidationError(\"artifact-factory source-pack batch response must be a JSON object.\")\n\n"
                    "    expected_contract_name = recipe_catalog.get(\"contractName\")\n"
                    "    expected_recipe_version = recipe_catalog.get(\"recipeVersion\")\n"
                    "    if response.get(\"contractName\") != expected_contract_name:\n"
                    "        raise LaunchValidationError(\n"
                    "            \"artifact-factory source-pack batch response contractName must match the recipe catalog contractName.\"\n"
                    "        )\n\n"
                    "    if response.get(\"recipeVersion\") != expected_recipe_version:\n"
                    "        raise LaunchValidationError(\n"
                    "            \"artifact-factory source-pack batch response recipeVersion must match the recipe catalog recipeVersion.\"\n"
                    "        )\n\n"
                    "    state = response.get(\"state\")\n"
                    "    if not isinstance(state, str) or not state.strip():\n"
                    "        raise LaunchValidationError(\"artifact-factory source-pack batch response must include a non-empty state.\")\n",
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
        self.assertIn("validate_batch_launch_response(response, recipe_catalog, payload)", result.stderr)

    def test_verifier_fails_closed_when_source_pack_batch_response_family_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-source-pack-response-family-") as temp_dir:
            temp_root = Path(temp_dir)
            for relative_path in SOURCE_FILES:
                source = REPO_ROOT / relative_path
                target = temp_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

            launcher_path = temp_root / "scripts/launch_artifact_factory_source_pack_batch.py"
            launcher_text = launcher_path.read_text(encoding="utf-8")
            launcher_path.write_text(
                launcher_text.replace(
                    "    required_families = normalize_string_list(response.get(\"requiredFamilies\"), \"requiredFamilies\")\n"
                    "    expected_required_families = normalize_string_list(\n"
                    "        normalized_payload.get(\"requiredFamilies\"),\n"
                    "        \"launch request requiredFamilies\",\n"
                    "    )\n"
                    "    if required_families != expected_required_families:\n"
                    "        raise LaunchValidationError(\n"
                    "            \"artifact-factory source-pack batch response requiredFamilies must match the launch request requiredFamilies.\"\n"
                    "        )\n\n"
                    "    families = normalize_string_list(response.get(\"families\"), \"families\")\n"
                    "    if families != expected_required_families:\n"
                    "        raise LaunchValidationError(\n"
                    "            \"artifact-factory source-pack batch response families must match the launch request requiredFamilies.\"\n"
                    "        )\n\n",
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
        self.assertIn("launch request requiredFamilies", result.stderr)

    def test_verifier_fails_closed_when_source_pack_batch_response_source_pack_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-source-pack-response-packids-") as temp_dir:
            temp_root = Path(temp_dir)
            for relative_path in SOURCE_FILES:
                source = REPO_ROOT / relative_path
                target = temp_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

            launcher_path = temp_root / "scripts/launch_artifact_factory_source_pack_batch.py"
            launcher_text = launcher_path.read_text(encoding="utf-8")
            launcher_path.write_text(
                launcher_text.replace(
                    "    source_pack_ids = normalize_string_list(response.get(\"sourcePackIds\"), \"sourcePackIds\")\n"
                    "    expected_source_pack_ids = sorted(\n"
                    "        {\n"
                    "            source_pack[\"sourcePackId\"].strip()\n"
                    "            for source_pack in normalized_payload[\"sourcePacks\"]\n"
                    "            if isinstance(source_pack, dict) and isinstance(source_pack.get(\"sourcePackId\"), str) and source_pack[\"sourcePackId\"].strip()\n"
                    "        }\n"
                    "    )\n"
                    "    if source_pack_ids != expected_source_pack_ids:\n"
                    "        raise LaunchValidationError(\n"
                    "            \"artifact-factory source-pack batch response sourcePackIds must match the launch request sourcePackIds.\"\n"
                    "        )\n\n",
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
        self.assertIn("launch request sourcePackIds", result.stderr)

    def test_verifier_fails_closed_when_batch_stable_segment_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-batch-id-proof-") as temp_dir:
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
                    "\n        if (!IsStablePublicShelfSegment(decoded))\n"
                    "        {\n"
                    "            throw new InvalidDataException(\n"
                    "                $\"artifact factory batch id '{batchId}' is unsafe; batch ids must use stable orchestration receipt segment characters.\");\n"
                    "        }\n",
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
        self.assertIn("batch ids must use stable orchestration receipt segment characters", result.stderr)

    def test_verifier_fails_closed_when_source_pack_stable_segment_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-source-pack-id-proof-") as temp_dir:
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
                    "\n        if (!IsStablePublicShelfSegment(decoded))\n"
                    "        {\n"
                    "            throw new InvalidDataException(\n"
                    "                $\"source pack id '{sourcePackId}' is unsafe; approved source-pack ids must use stable receipt segment characters.\");\n"
                    "        }\n",
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
        self.assertIn("approved source-pack ids must use stable receipt segment characters", result.stderr)

    def test_verifier_fails_closed_when_public_shelf_stable_segment_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-public-shelf-proof-") as temp_dir:
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
                    "\n            if (!IsStablePublicShelfSegment(decodedSegment))\n"
                    "            {\n"
                    "                throw new InvalidDataException(\n"
                    "                    $\"source pack '{sourcePackId}' has unsafe public proof shelf {fieldName} '{publicShelfRef}'; artifact factory bundle refs must use stable public proof shelf segment characters.\");\n"
                    "            }\n",
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
        self.assertIn("artifact factory bundle refs must use stable public proof shelf segment characters", result.stderr)

    def test_verifier_fails_closed_when_recipe_catalog_endpoint_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-recipe-endpoint-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            for relative_path in SOURCE_FILES:
                source = REPO_ROOT / relative_path
                target = temp_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

            controller_path = temp_root / "Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    '[HttpGet("/api/internal/artifact-factory/recipes")]',
                    '[HttpGet("/api/internal/artifact-factory/recipes-removed")]',
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
        self.assertIn("/api/internal/artifact-factory/recipes", result.stderr)

    def test_verifier_fails_closed_when_recipe_catalog_contract_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-recipe-catalog-proof-") as temp_dir:
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
                    "public ArtifactFactoryRecipeCatalogResult ListRecipes()",
                    "public ArtifactFactoryRecipeCatalogResult ListRecipeCatalogRemoved()",
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
        self.assertIn("ListRecipes", result.stderr)

    def test_verifier_fails_closed_when_release_bundle_public_route_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-release-route-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            for relative_path in SOURCE_FILES:
                source = REPO_ROOT / relative_path
                target = temp_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

            controller_path = temp_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    '[HttpGet("/artifacts/release-bundles/{releaseArtifactId}")]',
                    '[HttpGet("/artifacts/release-proof-missing/{releaseArtifactId}")]',
                ).replace(
                    'contractName = "chummer.run.public_proof_shelf.release_bundle.v1"',
                    'contractName = "chummer.run.public_proof_shelf.release_bundle.removed.v1"',
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
        self.assertIn("/artifacts/release-bundles/{releaseArtifactId}", result.stderr)
        self.assertIn("chummer.run.public_proof_shelf.release_bundle.v1", result.stderr)

    def test_verifier_fails_closed_when_release_bundle_format_route_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-release-format-route-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            for relative_path in SOURCE_FILES:
                source = REPO_ROOT / relative_path
                target = temp_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

            controller_path = temp_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    '[HttpGet("/artifacts/release-bundles/{releaseArtifactId}/{format}")]',
                    '[HttpGet("/artifacts/release-bundles/{releaseArtifactId}/format-removed/{format}")]',
                ).replace(
                    "publicProofShelfRef = normalizedFormat is null ? bundleRef : outputRefs[normalizedFormat]",
                    "publicProofShelfRef = bundleRef",
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
        self.assertIn("/artifacts/release-bundles/{releaseArtifactId}/{format}", result.stderr)
        self.assertIn("outputRefs[normalizedFormat]", result.stderr)

    def test_verifier_fails_closed_when_audience_locale_normalization_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-job-token-proof-") as temp_dir:
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
                    "        string audience = NormalizeAudience(request.Audience);\n"
                    "        string locale = NormalizeLocale(request.Locale);\n",
                    "        string audience = NormalizeOptional(request.Audience) ?? \"public-proof-shelf\";\n"
                    "        string locale = NormalizeOptional(request.Locale) ?? \"en-US\";\n",
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
        self.assertIn("NormalizeAudience", result.stderr)
        self.assertIn("NormalizeLocale", result.stderr)

    def test_verifier_fails_closed_when_job_token_safety_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-job-token-guard-") as temp_dir:
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
                    "\n    private static void RejectUnsafeJobToken(string value, string fieldName, bool allowComma)\n"
                    "    {\n"
                    "        string normalized = value.Trim();\n"
                    "        if (normalized.Length == 0)\n"
                    "        {\n"
                    "            throw new InvalidDataException($\"artifact factory {fieldName} is required.\");\n"
                    "        }\n\n"
                    "        if (normalized.Contains('?', StringComparison.Ordinal)\n"
                    "            || normalized.Contains('#', StringComparison.Ordinal)\n"
                    "            || normalized.Contains(':', StringComparison.Ordinal)\n"
                    "            || normalized.Contains('/', StringComparison.Ordinal)\n"
                    "            || normalized.Contains('\\\\', StringComparison.Ordinal))\n"
                    "        {\n"
                    "            throw new InvalidDataException(\n"
                    "                $\"artifact factory {fieldName} '{value}' is unsafe; job metadata must be stable source-pack tokens, not provider paths or URIs.\");\n"
                    "        }\n\n"
                    "        string decoded = Uri.UnescapeDataString(normalized);\n"
                    "        if (decoded is \".\" or \"..\"\n"
                    "            || decoded.Contains(':', StringComparison.Ordinal)\n"
                    "            || decoded.Contains('/', StringComparison.Ordinal)\n"
                    "            || decoded.Contains('\\\\', StringComparison.Ordinal))\n"
                    "        {\n"
                    "            throw new InvalidDataException(\n"
                    "                $\"artifact factory {fieldName} '{value}' is unsafe; job metadata must not contain traversal or encoded path separators.\");\n"
                    "        }\n\n"
                    "        foreach (char character in normalized)\n"
                    "        {\n"
                    "            if (char.IsLetterOrDigit(character)\n"
                    "                || character is '-' or '_' or '.'\n"
                    "                || (allowComma && character == ','))\n"
                    "            {\n"
                    "                continue;\n"
                    "            }\n\n"
                    "            throw new InvalidDataException(\n"
                    "                $\"artifact factory {fieldName} '{value}' is unsafe; job metadata must use stable token characters.\");\n"
                    "        }\n"
                    "    }\n",
                    "",
                ).replace(
                    "        RejectUnsafeJobToken(audience, \"audience\", allowComma: true);\n",
                    "",
                ).replace(
                    "        RejectUnsafeJobToken(locale, \"locale\", allowComma: false);\n",
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
        self.assertIn("RejectUnsafeJobToken", result.stderr)

    def test_verifier_fails_closed_when_requested_by_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-requested-by-proof-") as temp_dir:
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
                    "        string requestedBy = NormalizeRequestedBy(request.RequestedBy);\n",
                    "",
                    1,
                ).replace(
                    "                ? jobRequest with { RequestedBy = requestedBy }\n",
                    "                ? jobRequest with { RequestedBy = request.RequestedBy.Trim() }\n",
                ).replace(
                    "            RequestedBy: requestedBy,\n",
                    "            RequestedBy: request.RequestedBy.Trim(),\n",
                    1,
                ).replace(
                    "\n    private static string NormalizeRequestedBy(string? value)\n"
                    "    {\n"
                    "        string requestedBy = NormalizeOptional(value) ?? throw new InvalidDataException(\"requestedBy is required.\");\n"
                    "        RejectProviderSpecificRef(\"job-request\", requestedBy, \"requestedBy\");\n"
                    "        RejectUnsafeJobToken(requestedBy, \"requestedBy\", allowComma: false);\n"
                    "        return requestedBy;\n"
                    "    }\n",
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
        self.assertIn("NormalizeRequestedBy", result.stderr)

    def test_verifier_fails_closed_when_batch_requested_by_consistency_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-batch-requester-proof-") as temp_dir:
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
                    "            ArtifactFactoryJobLaunchRequest normalizedRequest;\n"
                    "            if (string.IsNullOrWhiteSpace(jobRequest.RequestedBy))\n"
                    "            {\n"
                    "                normalizedRequest = jobRequest with { RequestedBy = requestedBy };\n"
                    "            }\n"
                    "            else\n"
                    "            {\n"
                    "                string jobRequestedBy = NormalizeRequestedBy(jobRequest.RequestedBy);\n"
                    "                if (!string.Equals(jobRequestedBy, requestedBy, StringComparison.Ordinal))\n"
                    "                {\n"
                    "                    throw new InvalidDataException(\n"
                    "                        $\"artifact factory batch '{request.BatchId.Trim()}' job requestedBy '{jobRequestedBy}' must match batch requestedBy '{requestedBy}'.\");\n"
                    "                }\n\n"
                    "                normalizedRequest = jobRequest with { RequestedBy = jobRequestedBy };\n"
                    "            }\n\n",
                    "            ArtifactFactoryJobLaunchRequest normalizedRequest = string.IsNullOrWhiteSpace(jobRequest.RequestedBy)\n"
                    "                ? jobRequest with { RequestedBy = requestedBy }\n"
                    "                : jobRequest;\n",
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
        self.assertIn("must match batch requestedBy", result.stderr)

    def test_verifier_fails_closed_when_batch_media_requests_are_not_sorted_with_jobs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-batch-order-proof-") as temp_dir:
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
                    "        ArtifactFactoryJobLaunchResult[] orderedJobs = jobs\n"
                    "            .OrderBy(static job => job.JobId, StringComparer.OrdinalIgnoreCase)\n"
                    "            .ToArray();\n\n",
                    "",
                ).replace(
                    "            JobIds: orderedJobs.Select(static job => job.JobId).ToArray(),\n",
                    "            JobIds: jobs.Select(static job => job.JobId).Order(StringComparer.OrdinalIgnoreCase).ToArray(),\n",
                ).replace(
                    "            Jobs: orderedJobs,\n"
                    "            MediaFactoryRequests: orderedJobs.Select(static job => job.MediaFactoryRequest).ToArray());\n",
                    "            Jobs: jobs.OrderBy(static job => job.JobId, StringComparer.OrdinalIgnoreCase).ToArray(),\n"
                    "            MediaFactoryRequests: jobs.Select(static job => job.MediaFactoryRequest).ToArray());\n",
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
        self.assertIn("orderedJobs", result.stderr)

    def test_verifier_fails_closed_when_batch_required_families_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-required-families-proof-") as temp_dir:
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
                    "        string[] requiredFamilies = NormalizeRequiredBatchFamilies(request.RequiredFamilies);\n"
                    "        string[] missingRequiredFamilies = requiredFamilies\n"
                    "            .Where(required => !families.Contains(required, StringComparer.OrdinalIgnoreCase))\n"
                    "            .ToArray();\n"
                    "        if (missingRequiredFamilies.Length > 0)\n"
                    "        {\n"
                    "            throw new InvalidDataException(\n"
                    "                $\"artifact factory batch '{request.BatchId.Trim()}' is missing required recipe family job(s): {string.Join(\", \", missingRequiredFamilies)}.\");\n"
                    "        }\n\n",
                    "        string[] requiredFamilies = [];\n",
                ).replace(
                    "\n    private static string[] NormalizeRequiredBatchFamilies(IReadOnlyList<string>? requiredFamilies)\n"
                    "    {\n"
                    "        if (requiredFamilies is null || requiredFamilies.Count == 0)\n"
                    "        {\n"
                    "            return [];\n"
                    "        }\n\n"
                    "        string[] families = requiredFamilies\n"
                    "            .Select(NormalizeToken)\n"
                    "            .Where(static item => item.Length > 0)\n"
                    "            .Distinct(StringComparer.OrdinalIgnoreCase)\n"
                    "            .Order(StringComparer.OrdinalIgnoreCase)\n"
                    "            .ToArray();\n"
                    "        foreach (string family in families)\n"
                    "        {\n"
                    "            RejectProviderSpecificRef(\"batch-request\", family, \"requiredFamily\");\n"
                    "            RejectUnsafeJobToken(family, \"requiredFamily\", allowComma: false);\n"
                    "            if (!Recipes.ContainsKey(family))\n"
                    "            {\n"
                    "                throw new InvalidDataException($\"artifact factory batch requires unsupported recipe family '{family}'.\");\n"
                    "            }\n"
                    "        }\n\n"
                    "        return families;\n"
                    "    }\n",
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
        self.assertIn("missing required recipe family job(s)", result.stderr)

    def test_verifier_fails_closed_when_blank_required_families_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-blank-required-families-") as temp_dir:
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
                    "        if (families.Length == 0)\n"
                    "        {\n"
                    "            throw new InvalidDataException(\"artifact factory batch required recipe families cannot be empty.\");\n"
                    "        }\n\n",
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
        self.assertIn("required recipe families cannot be empty", result.stderr)

    def test_verifier_fails_closed_when_batch_required_families_result_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-required-families-result-proof-") as temp_dir:
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
                    "    IReadOnlyList<string> RequiredFamilies,\n",
                    "",
                ).replace(
                    "            RequiredFamilies: requiredFamilies,\n",
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
        self.assertIn("RequiredFamilies", result.stderr)

    def test_verifier_fails_closed_when_default_complete_batch_set_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-default-batch-proof-") as temp_dir:
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
                    "            return Recipes.Keys\n"
                    "                .Order(StringComparer.OrdinalIgnoreCase)\n"
                    "                .ToArray();\n",
                    "            return [];\n",
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
        self.assertIn("return Recipes.Keys", result.stderr)

    def test_verifier_fails_closed_when_download_shelf_release_bundle_remap_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-release-shelf-proof-") as temp_dir:
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
                    "            if (family.Equals(\"release\", StringComparison.OrdinalIgnoreCase)\n"
                    "                && TryBuildReleaseBundleRefFromDownloadShelfRef(shelfRef, out string? releaseBundleRef))\n"
                    "            {\n"
                    "                return releaseBundleRef;\n"
                    "            }\n\n",
                    "",
                ).replace(
                    "\n    private static bool TryBuildReleaseBundleRefFromDownloadShelfRef(string shelfRef, out string releaseBundleRef)\n"
                    "    {\n"
                    "        const string downloadInstallPrefix = \"/downloads/install/\";\n"
                    "        releaseBundleRef = string.Empty;\n"
                    "        if (!shelfRef.StartsWith(downloadInstallPrefix, StringComparison.OrdinalIgnoreCase))\n"
                    "        {\n"
                    "            return false;\n"
                    "        }\n\n"
                    "        string releaseArtifactId = shelfRef[downloadInstallPrefix.Length..].Trim('/');\n"
                    "        if (string.IsNullOrWhiteSpace(releaseArtifactId))\n"
                    "        {\n"
                    "            return false;\n"
                    "        }\n\n"
                    "        releaseBundleRef = $\"/artifacts/release-bundles/{Uri.EscapeDataString(releaseArtifactId)}\";\n"
                    "        return true;\n"
                    "    }\n",
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
        self.assertIn("TryBuildReleaseBundleRefFromDownloadShelfRef", result.stderr)

    def test_verifier_fails_closed_when_release_bundle_shelf_passthrough_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-release-bundle-shelf-proof-") as temp_dir:
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
                    "            if (family.Equals(\"release\", StringComparison.OrdinalIgnoreCase)\n"
                    "                && shelfRef.StartsWith(\"/artifacts/release-bundles/\", StringComparison.OrdinalIgnoreCase))\n"
                    "            {\n"
                    "                return shelfRef;\n"
                    "            }\n\n",
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
        self.assertIn("/artifacts/release-bundles/", result.stderr)

    def test_verifier_fails_closed_when_release_bundle_anchor_shape_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-release-anchor-proof-") as temp_dir:
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
                    "        if (family.Equals(\"release\", StringComparison.OrdinalIgnoreCase))\n"
                    "        {\n"
                    "            RejectReleaseBundleShelfAnchorShape(sourcePackId, publicShelfRef, fieldName);\n"
                    "        }\n",
                    "",
                ).replace(
                    "\n    private static void RejectReleaseBundleShelfAnchorShape(string sourcePackId, string publicShelfRef, string fieldName)\n"
                    "    {\n"
                    "        string[] allowedReleasePrefixes = [\"/downloads/install/\", \"/artifacts/release-bundles/\"];\n"
                    "        string? matchingPrefix = allowedReleasePrefixes.FirstOrDefault(prefix => publicShelfRef.StartsWith(prefix, StringComparison.OrdinalIgnoreCase));\n"
                    "        string releaseArtifactId = matchingPrefix is null\n"
                    "            ? string.Empty\n"
                    "            : publicShelfRef[matchingPrefix.Length..].Trim('/');\n\n"
                    "        if (string.IsNullOrWhiteSpace(releaseArtifactId)\n"
                    "            || releaseArtifactId.Contains('/', StringComparison.Ordinal)\n"
                    "            || releaseArtifactId.Contains('\\\\', StringComparison.Ordinal))\n"
                    "        {\n"
                    "            throw new InvalidDataException(\n"
                    "                $\"source pack '{sourcePackId}' has unsafe release public proof shelf {fieldName} '{publicShelfRef}'; release bundle anchors must resolve to exactly one release artifact segment.\");\n"
                    "        }\n"
                    "    }\n",
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
        self.assertIn("RejectReleaseBundleShelfAnchorShape", result.stderr)

    def test_verifier_fails_closed_when_non_release_shelf_anchor_shape_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-non-release-anchor-proof-") as temp_dir:
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
                    "\n    private static bool HasAnyResourceShelfAnchorShape(string publicShelfRef, IReadOnlyList<string> prefixes, bool allowBundlesSuffix)\n"
                    "        => prefixes.Any(prefix => HasResourceShelfAnchorShape(publicShelfRef, prefix, allowBundlesSuffix));\n\n"
                    "    private static bool HasResourceShelfAnchorShape(string publicShelfRef, string prefix, bool allowBundlesSuffix)\n"
                    "    {\n"
                    "        if (!publicShelfRef.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))\n"
                    "        {\n"
                    "            return false;\n"
                    "        }\n\n"
                    "        string remainder = publicShelfRef[prefix.Length..].Trim('/');\n"
                    "        if (string.IsNullOrWhiteSpace(remainder))\n"
                    "        {\n"
                    "            return false;\n"
                    "        }\n\n"
                    "        string[] segments = remainder.Split('/', StringSplitOptions.RemoveEmptyEntries);\n"
                    "        return segments.Length == 1\n"
                    "            || (allowBundlesSuffix\n"
                    "                && segments.Length == 2\n"
                    "                && segments[1].Equals(\"bundles\", StringComparison.OrdinalIgnoreCase));\n"
                    "    }\n",
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
        self.assertIn("HasResourceShelfAnchorShape", result.stderr)

    def test_verifier_fails_closed_when_output_shelf_refs_are_not_exposed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-output-shelf-proof-") as temp_dir:
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
                    "        publicProofShelfRefs.AddRange(BuildOutputShelfRefs(outputBindings));\n",
                    "",
                ).replace(
                    "\n    private static IEnumerable<string> BuildOutputShelfRefs(IReadOnlyList<ArtifactFactoryOutputBinding> outputBindings)\n"
                    "    {\n"
                    "        foreach (ArtifactFactoryOutputBinding binding in outputBindings)\n"
                    "        {\n"
                    "            int separatorIndex = binding.PublicRef.LastIndexOf('/');\n"
                    "            if (separatorIndex > 0)\n"
                    "            {\n"
                    "                yield return binding.PublicRef[..separatorIndex];\n"
                    "            }\n"
                    "        }\n"
                    "    }\n",
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
        self.assertIn("BuildOutputShelfRefs", result.stderr)

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

    def test_verifier_fails_closed_when_public_path_id_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-path-id-proof-") as temp_dir:
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
                    '        RejectUnsafePublicPathId(sourcePack.SourcePackId, sourcePack.ReleaseArtifactId, "releaseArtifactId");\n'
                    '        RejectUnsafePublicPathId(sourcePack.SourcePackId, sourcePack.SupportCaseId, "supportCaseId");\n'
                    '        RejectUnsafePublicPathId(sourcePack.SourcePackId, sourcePack.PublicationId, "publicationId");\n',
                    "",
                ).replace(
                    "\n    private static void RejectUnsafePublicPathId(string sourcePackId, string? value, string fieldName)\n"
                    "    {\n"
                    "        if (string.IsNullOrWhiteSpace(value))\n"
                    "        {\n"
                    "            return;\n"
                    "        }\n\n"
                    "        string pathId = value.Trim();\n"
                    "        if (pathId.Contains('?', StringComparison.Ordinal)\n"
                    "            || pathId.Contains('#', StringComparison.Ordinal)\n"
                    "            || pathId.Contains('/', StringComparison.Ordinal)\n"
                    "            || pathId.Contains('\\\\', StringComparison.Ordinal))\n"
                    "        {\n"
                    "            throw new InvalidDataException(\n"
                    "                $\"source pack '{sourcePackId}' has unsafe {fieldName} '{value}'; artifact factory path ids must be stable public proof shelf segments.\");\n"
                    "        }\n\n"
                    "        string decoded = Uri.UnescapeDataString(pathId);\n"
                    "        if (decoded is \".\" or \"..\"\n"
                    "            || decoded.Contains(':', StringComparison.Ordinal)\n"
                    "            || decoded.Contains('/', StringComparison.Ordinal)\n"
                    "            || decoded.Contains('\\\\', StringComparison.Ordinal))\n"
                    "        {\n"
                    "            throw new InvalidDataException(\n"
                    "                $\"source pack '{sourcePackId}' has unsafe {fieldName} '{value}'; artifact factory path ids must not contain traversal, encoded provider delimiters, or encoded path separators.\");\n"
                    "        }\n"
                    "    }\n",
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
        self.assertIn("RejectUnsafePublicPathId", result.stderr)

    def test_verifier_fails_closed_when_public_path_id_provider_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-path-id-provider-proof-") as temp_dir:
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
                    "        RejectProviderSpecificRef(sourcePackId, value, fieldName);\n\n",
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
        self.assertIn("RejectProviderSpecificRef(sourcePackId, value, fieldName)", result.stderr)

    def test_verifier_fails_closed_when_source_pack_id_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-source-pack-id-boundary-") as temp_dir:
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
                    '        RejectProviderSpecificRef(sourcePack.SourcePackId, sourcePack.SourcePackId, "sourcePackId");\n'
                    "        RejectUnsafeSourcePackId(sourcePack.SourcePackId);\n\n",
                    "",
                ).replace(
                    "private static void RejectUnsafeSourcePackId(string sourcePackId)",
                    "private static void RemovedRejectUnsafeSourcePackId(string sourcePackId)",
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
        self.assertIn("RejectUnsafeSourcePackId", result.stderr)

    def test_verifier_fails_closed_when_external_absolute_uri_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-external-uri-proof-") as temp_dir:
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
                    "\n        if (IsAbsoluteHttpRef(normalized) || IsUriLikeExternalRef(normalized, fieldName))\n"
                    "        {\n"
                    "            throw new InvalidDataException(\n"
                    "                $\"source pack '{sourcePackId}' has external absolute URI {fieldName} '{value}'; artifact factory jobs must launch from approved source-pack receipts instead of one-off provider flows.\");\n"
                    "        }\n",
                    "",
                ).replace(
                    "\n    private static bool IsAbsoluteHttpRef(string normalized)\n"
                    "        => Uri.TryCreate(normalized, UriKind.Absolute, out Uri? uri)\n"
                    "            && (uri.Scheme.Equals(Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)\n"
                    "                || uri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase));\n",
                    "",
                ).replace(
                    "\n    private static bool IsUriLikeExternalRef(string normalized, string fieldName)\n"
                    "        => !IsPublicShelfEvidenceRef(normalized, fieldName)\n"
                    "            && normalized.Contains(\"://\", StringComparison.Ordinal);\n",
                    "",
                ).replace(
                    "\n    private static bool IsPublicShelfEvidenceRef(string normalized, string fieldName)\n"
                    "        => fieldName.Equals(\"evidenceRef\", StringComparison.Ordinal)\n"
                    "            && normalized.StartsWith(\"public-shelf:\", StringComparison.OrdinalIgnoreCase);\n",
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
        self.assertIn("IsUriLikeExternalRef", result.stderr)

    def test_verifier_fails_closed_when_exact_provider_token_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-exact-provider-proof-") as temp_dir:
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
                    "        if (ProviderSpecificRefPrefixes.Contains(normalized)\n"
                    "            || ProviderSpecificRefPrefixes.Contains(prefix)\n",
                    "        if (ProviderSpecificRefPrefixes.Contains(prefix)\n",
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
        self.assertIn("ProviderSpecificRefPrefixes.Contains(normalized)", result.stderr)

    def test_verifier_fails_closed_when_provider_token_segment_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-provider-segment-proof-") as temp_dir:
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
                    "            || ProviderSpecificRefPrefixes.Contains(prefix)\n"
                    "            || (!IsExternalPublicShelfEvidenceRef(normalized, fieldName) && ContainsProviderSpecificToken(normalized)))\n",
                    "            || ProviderSpecificRefPrefixes.Contains(prefix))\n",
                ).replace(
                    "\n    private static bool ContainsProviderSpecificToken(string normalized)\n"
                    "    {\n"
                    "        string lower = normalized.ToLowerInvariant();\n"
                    "        foreach (string providerToken in ProviderSpecificRefPrefixes)\n"
                    "        {\n"
                    "            string token = providerToken.ToLowerInvariant();\n"
                    "            if (ContainsDelimitedToken(lower, token))\n"
                    "            {\n"
                    "                return true;\n"
                    "            }\n"
                    "        }\n\n"
                    "        return false;\n"
                    "    }\n\n"
                    "    private static bool ContainsDelimitedToken(string value, string token)\n"
                    "    {\n"
                    "        int startIndex = 0;\n"
                    "        while (startIndex < value.Length)\n"
                    "        {\n"
                    "            int index = value.IndexOf(token, startIndex, StringComparison.Ordinal);\n"
                    "            if (index < 0)\n"
                    "            {\n"
                    "                return false;\n"
                    "            }\n\n"
                    "            int endIndex = index + token.Length;\n"
                    "            if (IsProviderTokenBoundary(value, index - 1)\n"
                    "                && IsProviderTokenBoundary(value, endIndex))\n"
                    "            {\n"
                    "                return true;\n"
                    "            }\n\n"
                    "            startIndex = index + 1;\n"
                    "        }\n\n"
                    "        return false;\n"
                    "    }\n\n"
                    "    private static bool IsProviderTokenBoundary(string value, int index)\n"
                    "        => index < 0\n"
                    "            || index >= value.Length\n"
                    "            || value[index] is ':' or '/' or '\\\\' or '-' or '_' or '.';\n",
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
        self.assertIn("ContainsProviderSpecificToken", result.stderr)

    def test_verifier_fails_closed_when_external_public_shelf_boundary_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-public-shelf-boundary-proof-") as temp_dir:
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
                    "\n    private static bool IsExternalPublicShelfEvidenceRef(string normalized, string fieldName)\n"
                    "        => IsPublicShelfEvidenceRef(normalized, fieldName)\n"
                    "            && !normalized[\"public-shelf:\".Length..].TrimStart().StartsWith(\"/\", StringComparison.Ordinal);\n",
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
        self.assertIn("IsExternalPublicShelfEvidenceRef", result.stderr)

    def test_verifier_fails_closed_when_duplicate_source_pack_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-source-pack-proof-") as temp_dir:
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
                    "            string normalizedSourcePackId = sourcePack.SourcePackId.Trim();\n"
                    "            if (!sourcePackIds.Add(normalizedSourcePackId))\n"
                    "            {\n"
                    "                throw new InvalidDataException($\"duplicate source pack id '{normalizedSourcePackId}' is not allowed.\");\n"
                    "            }\n\n",
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
        self.assertIn("normalizedSourcePackId", result.stderr)

    def test_verifier_fails_closed_when_null_source_pack_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-null-source-pack-proof-") as temp_dir:
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
                    "            if (sourcePack is null)\n"
                    "            {\n"
                    "                throw new InvalidDataException(\"artifact factory job contains an empty approved source pack.\");\n"
                    "            }\n\n",
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
        self.assertIn("empty approved source pack", result.stderr)

    def test_verifier_fails_closed_when_receipt_prefix_boundary_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-receipt-prefix-boundary-") as temp_dir:
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
                    "            .Where(prefix => !requiredReceiptRefs.Any(receipt => ReceiptRefMatchesRequiredPrefix(receipt, prefix)))\n",
                    "            .Where(prefix => !requiredReceiptRefs.Any(receipt => receipt.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)))\n",
                ).replace(
                    "\n    private static bool ReceiptRefMatchesRequiredPrefix(string receiptRef, string requiredPrefix)\n"
                    "    {\n"
                    "        string normalizedReceiptRef = receiptRef.Trim();\n"
                    "        return normalizedReceiptRef.Equals(requiredPrefix, StringComparison.OrdinalIgnoreCase)\n"
                    "            || normalizedReceiptRef.StartsWith($\"{requiredPrefix}:\", StringComparison.OrdinalIgnoreCase);\n"
                    "    }\n",
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
        self.assertIn("ReceiptRefMatchesRequiredPrefix", result.stderr)

    def test_verifier_fails_closed_when_normalized_duplicate_source_pack_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-normalized-source-pack-proof-") as temp_dir:
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
                    "            string normalizedSourcePackId = sourcePack.SourcePackId.Trim();\n"
                    "            if (!sourcePackIds.Add(normalizedSourcePackId))\n"
                    "            {\n"
                    "                throw new InvalidDataException($\"duplicate source pack id '{normalizedSourcePackId}' is not allowed.\");\n"
                    "            }\n\n",
                    "            if (!sourcePackIds.Add(sourcePack.SourcePackId))\n"
                    "            {\n"
                    "                throw new InvalidDataException($\"duplicate source pack id '{sourcePack.SourcePackId}' is not allowed.\");\n"
                    "            }\n\n",
                ).replace(
                    "                SourcePackId: normalizedSourcePackId,\n",
                    "                SourcePackId: sourcePack.SourcePackId.Trim(),\n",
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
        self.assertIn("normalizedSourcePackId", result.stderr)

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

    def test_verifier_fails_closed_when_successor_registry_drops_source_pack_launcher_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-registry-launcher-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            registry_path = temp_root / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            registry_path.write_text(
                (
                    CANONICAL_SUCCESSOR_REGISTRY.read_text(encoding="utf-8")
                    .replace(
                        "          - /docker/chummercomplete/chummer6-hub/scripts/launch_artifact_factory_source_pack_batch.py preflights approved source-pack batches against the internal recipe catalog before launch.\n",
                        "",
                    )
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
        self.assertIn("launch_artifact_factory_source_pack_batch.py preflights approved source-pack batches", result.stderr)

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
                        "    completion_action: verify_closed_package_only",
                        "    do_not_reopen_reason: M107 chummer6-hub artifact factory orchestration is complete; future shards must verify this receipt, registry row, Fleet queue row, and design queue row instead of reopening the artifact-factory orchestration and public proof shelf release-bundles package.",
                        "    proof:",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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

    def test_verifier_fails_closed_when_queue_drops_source_pack_launcher_test_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-queue-launcher-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            queue_path = temp_root / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            queue_path.write_text(
                (
                    CANONICAL_FLEET_QUEUE.read_text(encoding="utf-8")
                    .replace(
                        "      - python3 -m unittest tests/test_artifact_factory_source_pack_launcher.py\n",
                        "",
                    )
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
        self.assertIn("test_artifact_factory_source_pack_launcher.py", result.stderr)

    def test_verifier_fails_closed_when_queue_uses_absolute_unittest_path_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-queue-absolute-unittest-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            queue_path = temp_root / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            queue_path.write_text(
                (
                    CANONICAL_FLEET_QUEUE.read_text(encoding="utf-8")
                    .replace(
                        "      - python3 -m unittest tests/test_artifact_factory_orchestration.py\n",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py\n",
                    )
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
        self.assertIn("forbidden active-run proof marker", result.stderr)
        self.assertIn(
            "python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
            result.stderr,
        )

    def test_verifier_fails_closed_when_queue_completion_action_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-queue-completion-action-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            queue_path.write_text(
                "\n".join(
                    [
                        "items:",
                        "  - title: Stand up artifact-factory orchestration for release, support, and publication bundles",
                        "    task: Launch recipe-backed release, fix, support, and publication artifact jobs from approved source packs instead of one-off provider flows.",
                        "    package_id: next90-m107-hub-artifact-factory",
                        "    milestone_id: 107",
                        "    wave: W9",
                        "    repo: chummer6-hub",
                        "    status: complete",
                        "    frontier_id: 1421219975",
                        "    landed_commit: b9e6b52e",
                        "    proof:",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
        self.assertIn("completion_action must be 'verify_closed_package_only'", result.stderr)

    def test_verifier_fails_closed_when_queue_wave_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-queue-wave-") as temp_dir:
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
                        "    frontier_id: 1421219975",
                        "    landed_commit: b9e6b52e",
                        "    completion_action: verify_closed_package_only",
                        "    do_not_reopen_reason: M107 chummer6-hub artifact factory orchestration is complete; future shards must verify this receipt, registry row, Fleet queue row, and design queue row instead of reopening the artifact-factory orchestration and public proof shelf release-bundles package.",
                        "    proof:",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
        self.assertIn("wave must be 'W9'", result.stderr)

    def test_verifier_fails_closed_when_queue_do_not_reopen_reason_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-queue-do-not-reopen-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            queue_path.write_text(
                "\n".join(
                    [
                        "items:",
                        "  - title: Stand up artifact-factory orchestration for release, support, and publication bundles",
                        "    task: Launch recipe-backed release, fix, support, and publication artifact jobs from approved source packs instead of one-off provider flows.",
                        "    package_id: next90-m107-hub-artifact-factory",
                        "    milestone_id: 107",
                        "    wave: W9",
                        "    repo: chummer6-hub",
                        "    status: complete",
                        "    frontier_id: 1421219975",
                        "    landed_commit: b9e6b52e",
                        "    completion_action: verify_closed_package_only",
                        "    proof:",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
        self.assertIn("do_not_reopen_reason must be", result.stderr)

    def test_verifier_fails_closed_when_queue_package_is_duplicated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-duplicate-queue-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            queue_path.write_text(
                "\n".join(
                    [
                        "items:",
                        "  - title: Stand up artifact-factory orchestration for release, support, and publication bundles",
                        "    package_id: next90-m107-hub-artifact-factory",
                        "    milestone_id: 107",
                        "  - title: Duplicate stale artifact-factory package",
                        "    package_id: next90-m107-hub-artifact-factory",
                        "    milestone_id: 107",
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
        self.assertIn("exactly one package_id next90-m107-hub-artifact-factory", result.stderr)

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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/MissingArtifactFactoryProofAnchor.cs",
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

    def test_verifier_fails_closed_when_proof_commit_anchor_is_not_on_current_branch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-branch-proof-") as temp_dir:
            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()
            fake_git = fake_bin / "git"
            fake_git.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "if [[ \"$1\" == \"-C\" ]]; then",
                        "  shift 2",
                        "fi",
                        "if [[ \"$1\" == \"cat-file\" && \"$2\" == \"-e\" ]]; then",
                        "  exit 0",
                        "fi",
                        "if [[ \"$1\" == \"merge-base\" && \"$2\" == \"--is-ancestor\" ]]; then",
                        "  exit 1",
                        "fi",
                        "exit 0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("commit proof anchor is not on the current branch", result.stderr)
        self.assertIn("commit b9e6b52e", result.stderr)

    def test_verifier_fails_closed_when_queue_frontier_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-frontier-proof-") as temp_dir:
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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
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
        self.assertIn("successor frontier 1421219975", result.stderr)

    def test_verifier_rejects_forbidden_active_run_proof_markers_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-forbidden-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.\n",
                    "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.\n"
                    "      - Operator Telemetry helper output from a worker run.\n",
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
        self.assertIn("forbidden active-run proof marker: operator telemetry", result.stderr)

    def test_verifier_fails_closed_when_structured_frontier_id_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-structured-frontier-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace("    frontier_id: 1421219975\n", ""),
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
        self.assertIn("frontier_id must be 1421219975", result.stderr)

    def test_verifier_fails_closed_when_queue_guard_commit_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-guard-commit-proof-") as temp_dir:
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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - /docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
        self.assertIn("commit cfd5d208", result.stderr)

    def test_verifier_fails_closed_when_latest_proof_guard_commit_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-latest-guard-proof-") as temp_dir:
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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - /docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
        self.assertIn("commit 60125d9e", result.stderr)

    def test_verifier_fails_closed_when_closeout_proof_commit_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-closeout-proof-") as temp_dir:
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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - /docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
        self.assertIn("commit c98a49f2", result.stderr)

    def test_verifier_fails_closed_when_closeout_guard_commit_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-closeout-guard-proof-") as temp_dir:
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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - /docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
        self.assertIn("commit 28d3e13f", result.stderr)

    def test_verifier_fails_closed_when_release_bundle_ref_guard_commit_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-release-bundle-ref-proof-") as temp_dir:
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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - /docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
        self.assertIn("commit 76b0c410", result.stderr)

    def test_verifier_fails_closed_when_duplicate_queue_guard_commit_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-duplicate-queue-proof-") as temp_dir:
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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - /docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "      - /docker/chummercomplete/chummer6-hub commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
        self.assertIn("commit f0bdfcb9", result.stderr)

    def test_verifier_fails_closed_when_latest_duplicate_queue_guard_commit_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-latest-duplicate-queue-proof-") as temp_dir:
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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - /docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "      - /docker/chummercomplete/chummer6-hub commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
        self.assertIn("commit 66b1a1c7", result.stderr)

    def test_verifier_fails_closed_when_current_duplicate_queue_guard_proof_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-current-duplicate-queue-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit 51623cd3 pins M107 artifact factory duplicate queue guard proof.\n",
                    "",
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
        self.assertIn("commit 51623cd3", result.stderr)

    def test_verifier_fails_closed_when_current_duplicate_queue_proof_guard_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-current-duplicate-queue-guard-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit 2b8a9431 tightens the current M107 duplicate queue proof guard.\n",
                    "",
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
        self.assertIn("commit 2b8a9431", result.stderr)

    def test_verifier_fails_closed_when_public_shelf_safety_commit_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-shelf-safety-proof-") as temp_dir:
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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - /docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "      - /docker/chummercomplete/chummer6-hub commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
        self.assertIn("commit a20aa910", result.stderr)

    def test_verifier_fails_closed_when_shelf_safety_pin_commit_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-shelf-pin-proof-") as temp_dir:
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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - /docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "      - /docker/chummercomplete/chummer6-hub commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit a20aa910 tightens M107 artifact factory public shelf ref safety.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
        self.assertIn("commit 7ce86602", result.stderr)

    def test_verifier_fails_closed_when_source_pack_guard_commit_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-source-pack-pin-proof-") as temp_dir:
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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - /docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "      - /docker/chummercomplete/chummer6-hub commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit a20aa910 tightens M107 artifact factory public shelf ref safety.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7ce86602 pins M107 artifact factory shelf safety proof.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
        self.assertIn("commit 326db197", result.stderr)

    def test_verifier_fails_closed_when_structured_frontier_guard_commit_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-structured-frontier-pin-proof-") as temp_dir:
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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - /docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "      - /docker/chummercomplete/chummer6-hub commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit a20aa910 tightens M107 artifact factory public shelf ref safety.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7ce86602 pins M107 artifact factory shelf safety proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit 326db197 tightens M107 artifact factory source-pack proof.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
        self.assertIn("commit bd67b5ff", result.stderr)

    def test_verifier_fails_closed_when_proof_hygiene_guard_commit_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-proof-hygiene-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit 6851982b tightens M107 artifact factory proof hygiene.\n",
                    "",
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
        self.assertIn("commit 6851982b", result.stderr)

    def test_verifier_fails_closed_when_branch_guard_commit_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-branch-guard-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit 5b901df5 tightens M107 artifact factory proof branch guard.\n",
                    "",
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
        self.assertIn("commit 5b901df5", result.stderr)

    def test_verifier_fails_closed_when_output_shelf_guard_commit_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-output-shelf-guard-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit cbae3cdd tightens M107 artifact factory output shelf proof.\n",
                    "",
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
        self.assertIn("commit cbae3cdd", result.stderr)

    def test_verifier_fails_closed_when_output_shelf_pin_commit_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-output-shelf-pin-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit f0142482 pins M107 artifact factory output shelf proof.\n",
                    "",
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
        self.assertIn("commit f0142482", result.stderr)

    def test_verifier_fails_closed_when_current_output_shelf_proof_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-current-output-shelf-pin-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit a66a06bb tightens M107 artifact output shelf proof pin.\n",
                    "",
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
        self.assertIn("commit a66a06bb", result.stderr)

    def test_verifier_fails_closed_when_latest_artifact_shelf_proof_floor_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-latest-shelf-proof-floor-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit 9a8e56f0 tightens M107 artifact shelf proof floor.\n",
                    "",
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
        self.assertIn("commit 9a8e56f0", result.stderr)

    def test_verifier_fails_closed_when_current_artifact_shelf_proof_floor_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-current-shelf-proof-floor-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit a929cc7d pins M107 artifact shelf proof floor.\n",
                    "",
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
        self.assertIn("commit a929cc7d", result.stderr)

    def test_verifier_fails_closed_when_current_m107_guard_floor_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-current-guard-floor-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit ff3100b4 requires the current M107 artifact shelf proof floor.\n",
                    "",
                ).replace(
                    "      - /docker/chummercomplete/chummer6-hub commit 94f0c9e1 pins M107 current duplicate queue guard.\n",
                    "",
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
        self.assertIn("commit ff3100b4", result.stderr)
        self.assertIn("commit 94f0c9e1", result.stderr)

    def test_verifier_fails_closed_when_source_pack_id_normalization_commit_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-source-pack-id-normalization-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit f22ce5a5 tightens M107 artifact factory source-pack id normalization.\n",
                    "",
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
        self.assertIn("commit f22ce5a5", result.stderr)

    def test_verifier_fails_closed_when_source_pack_id_proof_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-source-pack-id-proof-pin-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit b15c2193 pins M107 source pack id proof.\n",
                    "",
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
        self.assertIn("commit b15c2193", result.stderr)

    def test_verifier_fails_closed_when_artifact_path_id_guard_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-path-id-proof-pin-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit 9b032c87 tightens M107 artifact path id guards.\n",
                    "",
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
        self.assertIn("commit 9b032c87", result.stderr)

    def test_verifier_fails_closed_when_artifact_path_guard_proof_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-path-guard-proof-pin-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit f1ca6c1a pins M107 artifact path guard proof.\n",
                    "",
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
        self.assertIn("commit f1ca6c1a", result.stderr)

    def test_verifier_fails_closed_when_receipt_ref_guard_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-receipt-ref-proof-pin-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit a91ea733 tightens M107 artifact factory receipt refs.\n",
                    "",
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
        self.assertIn("commit a91ea733", result.stderr)

    def test_verifier_fails_closed_when_current_proof_floor_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-current-proof-floor-pin-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit c31258fa tightens M107 artifact factory proof floor.\n",
                    "",
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
        self.assertIn("commit c31258fa", result.stderr)

    def test_verifier_fails_closed_when_latest_proof_floor_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-latest-proof-floor-pin-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit 45d3d498 tightens M107 artifact factory proof floor.\n",
                    "",
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
        self.assertIn("commit 45d3d498", result.stderr)

    def test_verifier_fails_closed_when_current_pinned_proof_floor_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-current-pinned-proof-floor-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit c3aaf05a pins M107 artifact factory proof floor.\n",
                    "",
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
        self.assertIn("commit c3aaf05a", result.stderr)

    def test_verifier_fails_closed_when_current_guard_floor_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-current-guard-floor-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit 285e97be tightens the current M107 artifact factory proof floor guard.\n",
                    "",
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
        self.assertIn("commit 285e97be", result.stderr)

    def test_verifier_fails_closed_when_refreshed_guard_floor_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-refreshed-guard-floor-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit ce1c6611 pins M107 artifact factory proof floor guard.\n",
                    "",
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
        self.assertIn("commit ce1c6611", result.stderr)

    def test_verifier_fails_closed_when_latest_refreshed_guard_floor_pin_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-latest-refreshed-guard-floor-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit 67ae7dab requires refreshed M107 proof floor.\n",
                    "",
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
        self.assertIn("commit 67ae7dab", result.stderr)

    def test_verifier_fails_closed_when_pinned_refreshed_proof_floor_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-pinned-refreshed-proof-floor-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit 65ac67a8 pins M107 refreshed artifact factory proof floor.\n",
                    "",
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
        self.assertIn("commit 65ac67a8", result.stderr)

    def test_verifier_fails_closed_when_external_uri_guard_proof_floor_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-external-uri-guard-floor-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit e0121780 tightens M107 artifact factory external URI guard.\n",
                    "",
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
        self.assertIn("commit e0121780", result.stderr)

    def test_verifier_fails_closed_when_current_format_scope_proof_floor_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-format-scope-proof-floor-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            queue_path.write_text(
                queue_text.replace(
                    "      - /docker/chummercomplete/chummer6-hub commit 700343bc pins M107 format scope proof floor.\n",
                    "",
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
        self.assertIn("commit 700343bc", result.stderr)

    def test_verifier_fails_closed_when_fleet_and_design_queue_rows_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-queue-mirror-drift-") as temp_dir:
            design_queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            source_queue = Path("/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml")
            queue_text = source_queue.read_text(encoding="utf-8")
            design_queue_path.write_text(
                queue_text.replace(
                    "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.\n",
                    "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.\n"
                    "      - closed package proof mirror drift sentinel.\n",
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_ARTIFACT_FACTORY_DESIGN_QUEUE_STAGING"] = str(design_queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("queue mirror drift", result.stderr)
        self.assertIn("field proof", result.stderr)

    def test_verifier_fails_closed_when_design_queue_source_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-design-queue-proof-") as temp_dir:
            design_queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            design_queue_path.write_text(
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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
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
            env["CHUMMER_ARTIFACT_FACTORY_DESIGN_QUEUE_STAGING"] = str(design_queue_path)

            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(design_queue_path), result.stderr)
        self.assertIn("successor frontier 1421219975", result.stderr)

    def test_verifier_fails_closed_when_queue_uses_active_run_telemetry_as_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-queue-telemetry-proof-") as temp_dir:
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
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
                        "      - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
                        "      - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
                        "      - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
                        "      - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
                        "      - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
                        "      - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
                        "      - /docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer6-hub commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - /docker/chummercomplete/chummer6-hub commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "      - /docker/chummercomplete/chummer6-hub commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
                        "      - /var/lib/codex-fleet/chummer_design_supervisor/shard-13/ACTIVE_RUN_HANDOFF.generated.md",
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
        self.assertIn("forbidden active-run proof marker: /var/lib/codex-fleet", result.stderr)
        self.assertIn("forbidden active-run proof marker: ACTIVE_RUN_HANDOFF", result.stderr)

    def test_verifier_fails_closed_when_registry_uses_active_run_telemetry_as_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-registry-telemetry-proof-") as temp_dir:
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
                        "        title: Orchestrate recipe-backed artifact jobs from approved release, support, and publication packs.",
                        "        status: complete",
                        "        evidence:",
                        "          - /docker/chummercomplete/chummer6-hub commit cda8849a binds release, fix, support, and publication recipe jobs to stable public proof shelf output refs.",
                        "          - /docker/chummercomplete/chummer6-hub commit e25842ac tightens mixed source-pack output anchoring so release bundle refs always bind to an approved artifact-bearing source pack.",
                        "          - /docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards so approved local refs cannot cross from release or publication recipes onto the wrong shelf family.",
                        "          - /docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution so stale file or commit anchors cannot keep the completed package green.",
                        "          - /docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "          - /docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "          - /docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard.",
                        "          - /docker/chummercomplete/chummer6-hub commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "          - /docker/chummercomplete/chummer6-hub commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "          - /docker/chummercomplete/chummer6-hub commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "          - /docker/chummercomplete/chummer6-hub commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
                        "          - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
                        "          - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs rejects unapproved or provider-specific source packs and emits media-factory output bindings for preview, caption, packet, audio, and video formats.",
                        "          - /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs and Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs bind the recipe-backed job launcher to the internal authenticated Hub orchestration endpoint.",
                        "          - /docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs proves release, support, fix, and publication bundles route through approved source-pack receipts.",
                        "          - /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py fail-closes missing recipe families, internal endpoint auth, public proof shelf bundle refs, and anchored source-pack output selection.",
                        "          - python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py exits 0.",
                        "          - python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py exits 0.",
                        "          - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore exits 0.",
                        "          - TASK_LOCAL_TELEMETRY.generated.json active-run helper output",
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
        self.assertIn("forbidden active-run proof marker: TASK_LOCAL_TELEMETRY", result.stderr)
        self.assertIn("forbidden active-run proof marker: active-run helper", result.stderr)

    def test_verifier_fails_closed_when_queue_proof_cites_out_of_scope_repo_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-queue-scope-proof-") as temp_dir:
            queue_path = Path(temp_dir) / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            queue_path.write_text(
                CANONICAL_FLEET_QUEUE.read_text(encoding="utf-8").replace(
                    "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.\n",
                    "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.\n"
                    "      - /docker/chummercomplete/chummer-hub-registry/scripts/verify_next90_m101_registry_promotion_discipline.py\n",
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
        self.assertIn("out-of-scope repo citation /docker/chummercomplete/chummer-hub-registry/scripts/verify_next90_m101_registry_promotion_discipline.py", result.stderr)

    def test_verifier_fails_closed_when_registry_evidence_cites_out_of_scope_repo_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="artifact-factory-registry-scope-proof-") as temp_dir:
            registry_path = Path(temp_dir) / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
            registry_path.write_text(
                CANONICAL_SUCCESSOR_REGISTRY.read_text(encoding="utf-8").replace(
                    "          - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore exits 0.\n",
                    "          - dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore exits 0.\n"
                    "          - /docker/chummercomplete/chummer-hub-registry/scripts/verify_next90_m101_registry_promotion_discipline.py\n",
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
        self.assertIn("out-of-scope repo citation /docker/chummercomplete/chummer-hub-registry/scripts/verify_next90_m101_registry_promotion_discipline.py", result.stderr)


if __name__ == "__main__":
    unittest.main()
