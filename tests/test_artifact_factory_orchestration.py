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
    "scripts/verify_artifact_factory_orchestration.py",
    "scripts/ai/verify.sh",
    "Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
    "Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
    "Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
    "tests/test_artifact_factory_orchestration.py",
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
                    "            || decoded.Contains('/', StringComparison.Ordinal)\n"
                    "            || decoded.Contains('\\\\', StringComparison.Ordinal))\n"
                    "        {\n"
                    "            throw new InvalidDataException(\n"
                    "                $\"source pack '{sourcePackId}' has unsafe {fieldName} '{value}'; artifact factory path ids must not contain traversal or encoded path separators.\");\n"
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
                    "\n        if (IsAbsoluteHttpRef(normalized))\n"
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
        self.assertIn("IsAbsoluteHttpRef", result.stderr)

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
                        "      - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
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
                        "      - /docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
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
                        "      - /docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
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
                        "      - /docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard.",
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
                        "      - /docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit c98a49f2 tightens M107 artifact factory closeout proof.",
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
                        "      - /docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit 28d3e13f tightens M107 artifact factory closeout guard.",
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
                        "      - /docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "      - /docker/chummercomplete/chummer.run-services commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
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
                        "      - /docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "      - /docker/chummercomplete/chummer.run-services commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard.",
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
                    "      - /docker/chummercomplete/chummer.run-services commit 51623cd3 pins M107 artifact factory duplicate queue guard proof.\n",
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
                    "      - /docker/chummercomplete/chummer.run-services commit 2b8a9431 tightens the current M107 duplicate queue proof guard.\n",
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
                        "      - /docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "      - /docker/chummercomplete/chummer.run-services commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard.",
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
                        "      - /docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "      - /docker/chummercomplete/chummer.run-services commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit a20aa910 tightens M107 artifact factory public shelf ref safety.",
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
                        "      - /docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "      - /docker/chummercomplete/chummer.run-services commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit a20aa910 tightens M107 artifact factory public shelf ref safety.",
                        "      - /docker/chummercomplete/chummer.run-services commit 7ce86602 pins M107 artifact factory shelf safety proof.",
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
                        "      - /docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "      - /docker/chummercomplete/chummer.run-services commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit a20aa910 tightens M107 artifact factory public shelf ref safety.",
                        "      - /docker/chummercomplete/chummer.run-services commit 7ce86602 pins M107 artifact factory shelf safety proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit 326db197 tightens M107 artifact factory source-pack proof.",
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
                    "      - /docker/chummercomplete/chummer.run-services commit 6851982b tightens M107 artifact factory proof hygiene.\n",
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
                    "      - /docker/chummercomplete/chummer.run-services commit 5b901df5 tightens M107 artifact factory proof branch guard.\n",
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
                    "      - /docker/chummercomplete/chummer.run-services commit cbae3cdd tightens M107 artifact factory output shelf proof.\n",
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
                    "      - /docker/chummercomplete/chummer.run-services commit f0142482 pins M107 artifact factory output shelf proof.\n",
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
                    "      - /docker/chummercomplete/chummer.run-services commit a66a06bb tightens M107 artifact output shelf proof pin.\n",
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
                    "      - /docker/chummercomplete/chummer.run-services commit 9a8e56f0 tightens M107 artifact shelf proof floor.\n",
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
                    "      - /docker/chummercomplete/chummer.run-services commit a929cc7d pins M107 artifact shelf proof floor.\n",
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
                    "      - /docker/chummercomplete/chummer.run-services commit ff3100b4 requires the current M107 artifact shelf proof floor.\n",
                    "",
                ).replace(
                    "      - /docker/chummercomplete/chummer.run-services commit 94f0c9e1 pins M107 current duplicate queue guard.\n",
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
                    "      - /docker/chummercomplete/chummer.run-services commit f22ce5a5 tightens M107 artifact factory source-pack id normalization.\n",
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
                    "      - /docker/chummercomplete/chummer.run-services commit b15c2193 pins M107 source pack id proof.\n",
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
                    "      - /docker/chummercomplete/chummer.run-services commit 9b032c87 tightens M107 artifact path id guards.\n",
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
                    "      - /docker/chummercomplete/chummer.run-services commit f1ca6c1a pins M107 artifact path guard proof.\n",
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
                    "      - /docker/chummercomplete/chummer.run-services commit a91ea733 tightens M107 artifact factory receipt refs.\n",
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
                        "      - /docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "      - /docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "      - /docker/chummercomplete/chummer.run-services commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "      - /docker/chummercomplete/chummer.run-services commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "      - /docker/chummercomplete/chummer.run-services commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
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
                        "          - /docker/chummercomplete/chummer.run-services commit cda8849a binds release, fix, support, and publication recipe jobs to stable public proof shelf output refs.",
                        "          - /docker/chummercomplete/chummer.run-services commit e25842ac tightens mixed source-pack output anchoring so release bundle refs always bind to an approved artifact-bearing source pack.",
                        "          - /docker/chummercomplete/chummer.run-services commit b9e6b52e tightens recipe-specific public proof shelf route guards so approved local refs cannot cross from release or publication recipes onto the wrong shelf family.",
                        "          - /docker/chummercomplete/chummer.run-services commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution so stale file or commit anchors cannot keep the completed package green.",
                        "          - /docker/chummercomplete/chummer.run-services commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
                        "          - /docker/chummercomplete/chummer.run-services commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
                        "          - /docker/chummercomplete/chummer.run-services commit 60125d9e tightens M107 artifact factory proof guard.",
                        "          - /docker/chummercomplete/chummer.run-services commit c98a49f2 tightens M107 artifact factory closeout proof.",
                        "          - /docker/chummercomplete/chummer.run-services commit 28d3e13f tightens M107 artifact factory closeout guard.",
                        "          - /docker/chummercomplete/chummer.run-services commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
                        "          - /docker/chummercomplete/chummer.run-services commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
                        "          - successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
                        "          - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs rejects unapproved or provider-specific source packs and emits media-factory output bindings for preview, caption, packet, audio, and video formats.",
                        "          - /docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs and Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs bind the recipe-backed job launcher to the internal authenticated Hub orchestration endpoint.",
                        "          - /docker/chummercomplete/chummer.run-services/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs proves release, support, fix, and publication bundles route through approved source-pack receipts.",
                        "          - /docker/chummercomplete/chummer.run-services/scripts/verify_artifact_factory_orchestration.py fail-closes missing recipe families, internal endpoint auth, public proof shelf bundle refs, and anchored source-pack output selection.",
                        "          - python3 /docker/chummercomplete/chummer.run-services/scripts/verify_artifact_factory_orchestration.py exits 0.",
                        "          - python3 -m unittest /docker/chummercomplete/chummer.run-services/tests/test_artifact_factory_orchestration.py exits 0.",
                        "          - dotnet test /docker/chummercomplete/chummer.run-services/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore exits 0.",
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


if __name__ == "__main__":
    unittest.main()
