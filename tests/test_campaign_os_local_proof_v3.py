from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "campaign_os_local_proof_v3.py"
MATERIALIZER_PATH = REPO_ROOT / "scripts" / "materialize_campaign_os_local_proof.py"
VERIFIER_PATH = REPO_ROOT / "scripts" / "verify_campaign_os_local_proof.py"


def load_contract():
    spec = importlib.util.spec_from_file_location("campaign_os_local_proof_v3_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CONTRACT = load_contract()

EXPECTED_PROJECT_ROOTS = (
    "../chummer-core-engine/Chummer.Contracts",
    "../chummer-hub-registry/Chummer.Hub.Registry.Contracts",
    "../chummer-hub-registry/Chummer.Run.Registry",
    "../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts",
    "../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime",
    "Chummer.Play.Contracts",
    "Chummer.Campaign.Contracts",
    "Chummer.Control.Contracts",
    "Chummer.Run.Contracts",
    "Chummer.World.Contracts",
    "Chummer.Run.Api",
    "Chummer.Run.Identity",
    "Chummer.Run.AI",
)


class FakeOwnedExecutor:
    def __init__(self, dotnet_path: Path, csc_path: Path) -> None:
        self.dotnet_path = dotnet_path
        self.csc_path = csc_path
        self.prepare_exit_code = 0
        self.runner_exit_code = 0
        self.missing_runtime_path: str | None = None
        self.extra_runtime_path: str | None = None
        self.runtimeconfig_mode = "exact"
        self.checkpoint_mode = "exact"
        self.drift_runtime = False
        self.drift_source_path: Path | None = None
        self.drift_managed_path: Path | None = None
        self.drift_staged = False
        self.prepare_environment: dict[str, str] = {}
        self.run_environment: dict[str, str] = {}
        self.private_directory_modes: dict[str, int] = {}

    def resolve_csc(self, root, work_root, environment):  # noqa: ANN001
        self.prepare_environment = dict(environment)
        return self.csc_path

    def prepare(self, root, work_root, csc_path, environment, logs_root):  # noqa: ANN001
        self.prepare_environment = dict(environment)
        self.private_directory_modes = {
            name: os.stat(Path(work_root) / name).st_mode & 0o777
            for name in ("runtime", "build", "logs")
        }
        if self.prepare_exit_code != 0:
            return self.prepare_exit_code
        runtime = Path(work_root) / "runtime"
        for relative in CONTRACT.RUNTIME_CLOSURE_PATHS:
            if relative == self.missing_runtime_path:
                continue
            path = runtime / relative
            if relative == CONTRACT.RUNTIMECONFIG_FILE_NAME:
                runtime_options: dict[str, object] = {
                    "tfm": "net10.0",
                    "frameworks": [
                        {"name": "Microsoft.NETCore.App", "version": "10.0.1"},
                        {"name": "Microsoft.AspNetCore.App", "version": "10.0.1"},
                    ],
                }
                if self.runtimeconfig_mode == "wrong_framework":
                    frameworks = runtime_options["frameworks"]
                    assert isinstance(frameworks, list) and isinstance(frameworks[1], dict)
                    frameworks[1]["name"] = "Untrusted.Framework"
                elif self.runtimeconfig_mode == "wrong_version":
                    frameworks = runtime_options["frameworks"]
                    assert isinstance(frameworks, list) and isinstance(frameworks[0], dict)
                    frameworks[0]["version"] = "10.0.0"
                elif self.runtimeconfig_mode == "untrusted_roll_forward":
                    runtime_options["rollForward"] = "LatestMajor"
                path.write_text(
                    json.dumps({"runtimeOptions": runtime_options}, separators=(",", ":")) + "\n",
                    encoding="utf-8",
                )
            else:
                path.write_bytes(b"MZ\x00" + relative.encode("ascii"))
        if self.extra_runtime_path is not None:
            (runtime / self.extra_runtime_path).write_bytes(b"unexpected")
        return 0

    def execute(self, root, assembly_path, environment, logs_root):  # noqa: ANN001
        self.run_environment = dict(environment)
        if self.drift_runtime:
            Path(assembly_path).write_bytes(Path(assembly_path).read_bytes() + b"drift")
        if self.drift_source_path is not None:
            self.drift_source_path.write_bytes(self.drift_source_path.read_bytes() + b"drift")
        if self.drift_managed_path is not None:
            self.drift_managed_path.write_bytes(self.drift_managed_path.read_bytes() + b"drift")
        if self.drift_staged:
            candidate_root = Path(environment["CHUMMER_CAMPAIGN_OS_CANDIDATE_ROOT"])
            (candidate_root / "Chummer.Run.Api" / "late-file.cs").write_text("late\n", encoding="utf-8")
        if self.runner_exit_code != 0:
            return self.runner_exit_code
        checkpoint_path = Path(environment["CHUMMER_CAMPAIGN_OS_CHECKPOINT_OUT"])
        run_id = environment["CHUMMER_CAMPAIGN_OS_RUN_ID"]
        checkpoints = [
            {
                "checkpoint_id": CONTRACT.CHECKPOINT_IDS[journey_id],
                "run_id": run_id,
                "status": "passed",
            }
            for journey_id in CONTRACT.JOURNEY_IDS
        ]
        if self.checkpoint_mode in {"missing", "skipped"}:
            checkpoints.pop()
        elif self.checkpoint_mode == "duplicate":
            checkpoints[-1] = dict(checkpoints[0])
        elif self.checkpoint_mode == "unknown":
            checkpoints[-1]["checkpoint_id"] = "unknown.run_services_smoke_exit_zero"
        elif self.checkpoint_mode == "wrong_run":
            checkpoints[-1]["run_id"] = str(uuid.uuid4())
        elif self.checkpoint_mode == "noncanonical_json":
            checkpoint_path.write_text(
                "".join(json.dumps(item) + "\n" for item in checkpoints),
                encoding="utf-8",
            )
            return 0
        checkpoint_path.write_text(
            "".join(
                json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
                for item in checkpoints
            ),
            encoding="utf-8",
        )
        return 0


class CampaignOsLocalProofV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "workspace"
        self.complete_root = self.workspace / "chummercomplete"
        self.root = self.complete_root / "chummer.run-services"
        self.root.mkdir(parents=True)
        for directory in (
            self.root / "scripts" / "ai",
            self.root / "tests" / "RunServicesSmoke",
            self.root / ".codex-design" / "product",
            self.root / ".codex-studio" / "published",
        ):
            directory.mkdir(parents=True, exist_ok=True)

        for source in (MODULE_PATH, MATERIALIZER_PATH, VERIFIER_PATH):
            shutil.copyfile(source, self.root / "scripts" / source.name)
        for relative in (
            "scripts/ai/run_services_smoke.sh",
            "scripts/ai/prepare_run_services_smoke.sh",
            "scripts/ai/_env.sh",
            "scripts/ai/build_r1_cleanroom.sh",
        ):
            shutil.copyfile(REPO_ROOT / relative, self.root / relative)

        self.source = self.root / CONTRACT.SOURCE_PATH
        shutil.copyfile(REPO_ROOT / CONTRACT.SOURCE_PATH, self.source)
        self.spec = self.root / CONTRACT.JOURNEY_SPEC_PATH
        lines = ["product: chummer", "version: 1", "journey_gates:"]
        for journey in CONTRACT.JOURNEY_IDS:
            lines.extend((f"  - id: {journey}", f"    title: {journey}"))
        self.spec.write_text("\n".join(lines) + "\n", encoding="utf-8")
        (self.root / "scripts" / "runbook.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

        product_source = self.complete_root / "chummer-design" / "products" / "chummer"
        product_source.mkdir(parents=True)
        (product_source / "guide.md").write_text("candidate product guide\n", encoding="utf-8")

        for project_root, project_file, package_root in CONTRACT.PROJECT_SPECS:
            project_directory = (self.root / project_root).resolve()
            project_directory.mkdir(parents=True, exist_ok=True)
            assembly_name = (
                "<AssemblyName>Chummer.Engine.Contracts</AssemblyName>"
                if project_file == "Chummer.Contracts.csproj"
                else ""
            )
            (project_directory / project_file).write_text(
                '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
                f'<TargetFramework>net10.0</TargetFramework>{assembly_name}'
                '</PropertyGroup></Project>\n',
                encoding="utf-8",
            )
            (project_directory / "Source.cs").write_text(
                f"namespace Smoke.{project_file.replace('.', '_')};\n",
                encoding="utf-8",
            )
            cache_root = (self.root / package_root).resolve()
            cache_root.mkdir(parents=True, exist_ok=True)
            libraries: dict[str, object] = {}
            if project_root == "Chummer.Run.Api":
                libraries["fake.package/1.0.0"] = {
                    "type": "package",
                    "path": "fake.package/1.0.0",
                    "files": ["lib/net10.0/Fake.Package.dll"],
                }
                package_directory = cache_root / "fake.package" / "1.0.0"
                (package_directory / "lib" / "net10.0").mkdir(parents=True, exist_ok=True)
                (package_directory / "lib" / "net10.0" / "Fake.Package.dll").write_bytes(b"fake-package")
                (package_directory / "fake.package.1.0.0.nupkg").write_bytes(b"fake-nupkg")
            object_directory = project_directory / "obj"
            object_directory.mkdir(exist_ok=True)
            assets = {
                "version": 3,
                "targets": {".NETCoreApp,Version=v10.0": {}},
                "libraries": libraries,
                "packageFolders": {str(cache_root) + os.sep: {}},
                "logs": [],
                "project": {
                    "restore": {
                        "projectUniqueName": str(project_directory / project_file),
                        "projectPath": str(project_directory / project_file),
                        "packagesPath": str(cache_root),
                        "outputPath": str(object_directory) + os.sep,
                        "frameworks": {
                            "net10.0": {
                                "projectReferences": {},
                            },
                        },
                    },
                },
            }
            (object_directory / "project.assets.json").write_text(
                json.dumps(assets, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            (object_directory / f"{project_file}.nuget.g.props").write_text(
                (
                    '<Project ToolsVersion="14.0"><PropertyGroup '
                    'Condition=" &apos;$(ExcludeRestorePackageImports)&apos; != &apos;true&apos; ">'
                    '<RestoreSuccess Condition=" &apos;$(RestoreSuccess)&apos; == &apos;&apos; ">True</RestoreSuccess>'
                    '<RestoreTool Condition=" &apos;$(RestoreTool)&apos; == &apos;&apos; ">NuGet</RestoreTool>'
                    '<ProjectAssetsFile Condition=" &apos;$(ProjectAssetsFile)&apos; == &apos;&apos; ">'
                    '$(MSBuildThisFileDirectory)project.assets.json</ProjectAssetsFile>'
                    '<NuGetPackageRoot Condition=" &apos;$(NuGetPackageRoot)&apos; == &apos;&apos; ">'
                    f'{cache_root}</NuGetPackageRoot>'
                    '<NuGetPackageFolders Condition=" &apos;$(NuGetPackageFolders)&apos; == &apos;&apos; ">'
                    f'{cache_root}</NuGetPackageFolders>'
                    '<NuGetProjectStyle Condition=" &apos;$(NuGetProjectStyle)&apos; == &apos;&apos; ">'
                    'PackageReference</NuGetProjectStyle>'
                    '<NuGetToolVersion Condition=" &apos;$(NuGetToolVersion)&apos; == &apos;&apos; ">'
                    '7.0.0</NuGetToolVersion>'
                    "</PropertyGroup><ItemGroup "
                    'Condition=" &apos;$(ExcludeRestorePackageImports)&apos; != &apos;true&apos; ">'
                    f'<SourceRoot Include="{cache_root}/" />'
                    "</ItemGroup></Project>\n"
                ),
                encoding="utf-8",
            )
            (object_directory / f"{project_file}.nuget.g.targets").write_text(
                '<Project ToolsVersion="14.0" />\n',
                encoding="utf-8",
            )

        (self.root / CONTRACT.REGISTRY_GLOBAL_USINGS_PATH).write_text(
            "global using Chummer.Run.Contracts.Registry;\n",
            encoding="utf-8",
        )

        tool_root = self.workspace / "toolchain"
        tool_root.mkdir()
        self.dotnet = tool_root / "dotnet"
        self.dotnet.write_bytes(b"fake-dotnet-host")
        component_files = (
            tool_root / "host" / "fxr" / "10.0.1" / "libhostfxr.so",
            tool_root / "shared" / "Microsoft.NETCore.App" / "10.0.1" / "System.Runtime.dll",
            tool_root / "shared" / "Microsoft.AspNetCore.App" / "10.0.1" / "Microsoft.AspNetCore.dll",
            tool_root / "packs" / "Microsoft.NETCore.App.Ref" / "10.0.1" / "ref" / "net10.0" / "System.Runtime.dll",
            tool_root / "packs" / "Microsoft.AspNetCore.App.Ref" / "10.0.1" / "ref" / "net10.0" / "Microsoft.AspNetCore.dll",
            tool_root / "sdk" / "10.0.100" / "MSBuild.dll",
        )
        for component_file in component_files:
            component_file.parent.mkdir(parents=True, exist_ok=True)
            component_file.write_bytes(f"managed:{component_file.name}".encode("utf-8"))
        self.csc = tool_root / "sdk" / "10.0.100" / "Roslyn" / "bincore" / "csc.dll"
        self.csc.parent.mkdir(parents=True)
        self.csc.write_bytes(b"fake-csc")
        self.original_dotnet = CONTRACT.DOTNET_HOST_PATH
        CONTRACT.DOTNET_HOST_PATH = self.dotnet
        self.executor = FakeOwnedExecutor(self.dotnet, self.csc)
        self.receipt = self.root / CONTRACT.DEFAULT_RECEIPT_PATH

    def tearDown(self) -> None:
        CONTRACT.DOTNET_HOST_PATH = self.original_dotnet
        self.temporary.cleanup()

    def run_owned(self, executor: FakeOwnedExecutor | None = None):  # noqa: ANN001
        return CONTRACT.run_owned_smoke(
            self.root,
            self.receipt,
            executor=executor or self.executor,
        )

    def payload(self) -> dict[str, object]:
        return json.loads(self.receipt.read_text(encoding="utf-8"))

    def write_payload(self, payload: dict[str, object]) -> None:
        self.receipt.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def validate(self, **kwargs):  # noqa: ANN003, ANN201
        return CONTRACT.validate_passed_receipt(self.root, self.receipt, **kwargs)

    def assert_running_failure(self, reason: str) -> dict[str, object]:
        payload = self.payload()
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["execution"]["failure_reason"], reason)
        self.assertFalse(self.validate().valid)
        return payload

    def test_public_cli_exposes_only_authoritative_run(self) -> None:
        for forbidden in ("begin", "complete"):
            result = subprocess.run(
                [sys.executable, "-I", "-S", str(MATERIALIZER_PATH), forbidden],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
        self.assertFalse(hasattr(CONTRACT, "begin_receipt"))
        self.assertFalse(hasattr(CONTRACT, "complete_receipt"))
        production_receipt = REPO_ROOT / CONTRACT.DEFAULT_RECEIPT_PATH
        before = production_receipt.read_bytes()
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "executor_override_forbidden"):
            CONTRACT.run_owned_smoke(
                REPO_ROOT,
                production_receipt,
                executor=self.executor,
            )
        self.assertEqual(production_receipt.read_bytes(), before)

    def test_dummy_assembly_and_output_override_cannot_mint(self) -> None:
        dummy = self.workspace / "RunServicesSmoke.dll"
        dummy.write_bytes(b"dummy")
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                str(MATERIALIZER_PATH),
                "--out",
                str(self.receipt),
                "complete",
                "--assembly",
                str(dummy),
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env={
                **os.environ,
                "CHUMMER_CAMPAIGN_OS_LOCAL_PROOF_OUT": str(self.receipt),
                "CHUMMER_SKIP_CLEANROOM_BUILD": "1",
                "PYTHON_BIN": str(dummy),
                "PATH": str(self.workspace),
            },
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.receipt.exists())

    def test_exact_owned_execution_passes_and_validates(self) -> None:
        payload = self.run_owned()
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["proof_kind"], CONTRACT.PROOF_KIND)
        self.assertEqual(payload["contract_version"], 3)
        self.assertEqual(CONTRACT.PROJECT_ROOTS, EXPECTED_PROJECT_ROOTS)
        self.assertEqual(payload["invocation"]["dependency_mode"], CONTRACT.DEPENDENCY_MODE)
        self.assertEqual(payload["execution"]["phase"], "verified")
        self.assertTrue(payload["execution"]["candidate_source_build_inputs_stable"])
        self.assertTrue(payload["execution"]["staged_candidate_inputs_stable"])
        self.assertTrue(payload["execution"]["managed_dotnet_closure_stable"])
        self.assertTrue(payload["execution"]["runtime_closure_stable"])
        self.assertEqual(
            payload["execution"]["candidate_source_build_inputs_before"]["project_root_count"],
            13,
        )
        self.assertEqual(
            payload["execution"]["managed_dotnet_closure_before"]["component_count"],
            6,
        )
        self.assertEqual(
            [item["checkpoint_id"] for item in payload["execution"]["runtime_checkpoints"]],
            [CONTRACT.CHECKPOINT_IDS[item] for item in CONTRACT.JOURNEY_IDS],
        )
        self.assertEqual(
            tuple(item["path"] for item in payload["execution"]["runtime_manifest_before"]["entries"]),
            CONTRACT.MANIFEST_PATHS,
        )
        self.assertTrue(self.validate().valid)
        self.assertEqual(self.executor.prepare_environment["PATH"], "/usr/bin:/bin")
        self.assertNotIn("CHUMMER_SKIP_CLEANROOM_BUILD", self.executor.prepare_environment)
        self.assertNotIn("CHUMMER_CAMPAIGN_OS_LOCAL_PROOF_OUT", self.executor.run_environment)
        self.assertEqual(self.executor.prepare_environment["CHUMMER_BUILD_NO_RESTORE"], "1")
        self.assertEqual(self.executor.prepare_environment["CHUMMER_BUILD_SOLUTION"], "0")
        self.assertEqual(
            self.executor.prepare_environment["DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE"],
            "1",
        )
        self.assertTrue(Path(self.executor.run_environment["CHUMMER_CAMPAIGN_OS_CANDIDATE_ROOT"]).is_absolute())
        self.assertEqual(
            self.executor.private_directory_modes,
            {"runtime": 0o700, "build": 0o700, "logs": 0o700},
        )

    def test_prepare_nonzero_leaves_running(self) -> None:
        self.executor.prepare_exit_code = 9
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "prepare_nonzero"):
            self.run_owned()
        payload = self.assert_running_failure("prepare_nonzero")
        self.assertEqual(payload["invocation"]["prepare_exit_code"], 9)

    def test_missing_or_extra_runtime_file_leaves_running(self) -> None:
        for missing, extra, reason in (
            (CONTRACT.ASSEMBLY_FILE_NAME, None, "runtime_closure_set_mismatch"),
            (None, "unexpected.dll", "runtime_closure_set_mismatch"),
        ):
            with self.subTest(missing=missing, extra=extra):
                self.executor.missing_runtime_path = missing
                self.executor.extra_runtime_path = extra
                with self.assertRaises(CONTRACT.ProofContractError):
                    self.run_owned()
                self.assert_running_failure(reason)
                self.executor.missing_runtime_path = None
                self.executor.extra_runtime_path = None

    def test_runtimeconfig_framework_selection_is_bound(self) -> None:
        for mode, reason in (
            ("wrong_framework", "runtimeconfig_framework_mismatch"),
            ("wrong_version", "runtimeconfig_framework_mismatch"),
            ("untrusted_roll_forward", "runtimeconfig_framework_policy_untrusted"),
        ):
            with self.subTest(mode=mode):
                self.executor.runtimeconfig_mode = mode
                with self.assertRaisesRegex(CONTRACT.ProofContractError, reason):
                    self.run_owned()
                self.assert_running_failure(reason)

    def test_runner_nonzero_and_closure_drift_leave_running(self) -> None:
        self.executor.runner_exit_code = 5
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "runner_nonzero"):
            self.run_owned()
        payload = self.assert_running_failure("runner_nonzero")
        self.assertEqual(payload["invocation"]["runner_exit_code"], 5)

        self.executor.runner_exit_code = 0
        self.executor.drift_runtime = True
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "runtime_closure_drift"):
            self.run_owned()
        self.assert_running_failure("runtime_closure_drift")

    def test_checkpoint_missing_duplicate_unknown_wrong_run_and_noncanonical_fail(self) -> None:
        for mode, reason in (
            ("missing", "runtime_checkpoint_set_mismatch"),
            ("skipped", "runtime_checkpoint_set_mismatch"),
            ("duplicate", "runtime_checkpoint_set_mismatch"),
            ("unknown", "runtime_checkpoint_set_mismatch"),
            ("wrong_run", "runtime_checkpoint_set_mismatch"),
            ("noncanonical_json", "checkpoint_log_semantic_mismatch"),
        ):
            with self.subTest(mode=mode):
                self.executor.checkpoint_mode = mode
                with self.assertRaises(CONTRACT.ProofContractError):
                    self.run_owned()
                self.assert_running_failure(reason)

    def test_current_input_drift_and_symlink_are_rejected(self) -> None:
        self.run_owned()
        runner = self.root / CONTRACT.RUNNER_PATH
        runner.write_text(runner.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")
        result = self.validate()
        self.assertFalse(result.valid)
        self.assertEqual(result.reason_code, "runner_identity_mismatch")

        runner.unlink()
        runner.symlink_to(REPO_ROOT / CONTRACT.RUNNER_PATH)
        self.receipt.unlink()
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "input_symlink"):
            self.run_owned()

    def test_post_mint_source_extra_and_symlink_are_rejected(self) -> None:
        self.run_owned()
        source = self.root / "Chummer.Run.Api" / "Source.cs"
        original = source.read_bytes()
        source.write_bytes(original + b"// post-mint drift\n")
        self.assertEqual(
            self.validate().reason_code,
            "candidate_source_build_inputs_current_mismatch",
        )

        source.write_bytes(original)
        extra = self.root / "Chummer.Run.Api" / "late-source.cs"
        extra.write_text("// late\n", encoding="utf-8")
        self.assertEqual(
            self.validate().reason_code,
            "candidate_source_build_inputs_current_mismatch",
        )

        extra.unlink()
        self.receipt.unlink()
        symlink = self.root / "Chummer.Run.Api" / "linked-source.cs"
        symlink.symlink_to(self.root / "Chummer.Run.Api" / "Source.cs")
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "candidate_project_tree_symlink"):
            self.run_owned()

    def test_framework_ref_sdk_and_package_drift_are_rejected(self) -> None:
        self.run_owned()
        managed_paths = (
            self.workspace / "toolchain" / "shared" / "Microsoft.NETCore.App" / "10.0.1" / "System.Runtime.dll",
            self.workspace / "toolchain" / "packs" / "Microsoft.NETCore.App.Ref" / "10.0.1" / "ref" / "net10.0" / "System.Runtime.dll",
            self.csc,
        )
        for path in managed_paths:
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(original + b"drift")
                self.assertEqual(
                    self.validate().reason_code,
                    "managed_dotnet_closure_current_mismatch",
                )
                path.write_bytes(original)

        package = self.root / ".tmp" / "nuget" / "packages" / "fake.package" / "1.0.0" / "lib" / "net10.0" / "Fake.Package.dll"
        original_package = package.read_bytes()
        package.write_bytes(original_package + b"drift")
        self.assertEqual(
            self.validate().reason_code,
            "candidate_source_build_inputs_current_mismatch",
        )
        package.write_bytes(original_package)

        assets = self.root / "Chummer.Run.Api" / "obj" / "project.assets.json"
        assets.write_bytes(assets.read_bytes() + b" \n")
        self.assertEqual(
            self.validate().reason_code,
            "candidate_source_build_inputs_current_mismatch",
        )

    def test_stable_managed_versions_win_over_preview_and_nested_ref_decoys(self) -> None:
        tool_root = self.dotnet.parent
        preview_files = (
            tool_root / "host" / "fxr" / "10.0.1-preview.10" / "libhostfxr.so",
            tool_root / "shared" / "Microsoft.NETCore.App" / "10.0.1-preview.10" / "System.Runtime.dll",
            tool_root / "shared" / "Microsoft.AspNetCore.App" / "10.0.1-preview.10" / "Microsoft.AspNetCore.dll",
            tool_root / "packs" / "Microsoft.NETCore.App.Ref" / "10.0.1-preview.10" / "ref" / "net10.0" / "System.Runtime.dll",
            tool_root / "packs" / "Microsoft.AspNetCore.App.Ref" / "10.0.1-preview.10" / "ref" / "net10.0" / "Microsoft.AspNetCore.dll",
            tool_root / "sdk" / "10.0.100-preview.10" / "Roslyn" / "bincore" / "csc.dll",
        )
        for path in preview_files:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"preview-decoy")
        nested_ref = tool_root / "packs" / "Microsoft.NETCore.App.Ref" / "10.0.1" / "zz" / "ref" / "net10.0" / "Decoy.dll"
        nested_ref.parent.mkdir(parents=True)
        nested_ref.write_bytes(b"nested-decoy")

        closure = CONTRACT._managed_dotnet_closure(self.dotnet)
        self.assertEqual(
            [item["version"] for item in closure["components"]],
            ["10.0.1", "10.0.1", "10.0.1", "10.0.1", "10.0.1", "10.0.100"],
        )
        netcore_ref = closure["components"][3]
        self.assertEqual(
            netcore_ref["path"],
            str(tool_root / "packs" / "Microsoft.NETCore.App.Ref" / "10.0.1" / "ref" / "net10.0"),
        )

    def test_explicit_msbuild_imports_are_rejected(self) -> None:
        project_root, project_file, _package_root = CONTRACT.PROJECT_SPECS[0]
        generated_target = self.root / project_root / "obj" / f"{project_file}.nuget.g.targets"
        generated_target.write_text(
            '<Project><Import Project="/tmp/unbound-package.targets" /></Project>\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "msbuild_definition_untrusted"):
            self.run_owned()

    def test_msbuild_output_redirection_is_rejected(self) -> None:
        project_root, project_file, _package_root = CONTRACT.PROJECT_SPECS[0]
        project = self.root / project_root / project_file
        project.write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            '<TargetFramework>net10.0</TargetFramework>'
            '<AssemblyName>Chummer.Engine.Contracts</AssemblyName>'
            '<OutputPath>/tmp/unbound-output/</OutputPath>'
            '</PropertyGroup></Project>\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "msbuild_property_untrusted"):
            CONTRACT._candidate_source_build_inputs(self.root)

    def test_external_msbuild_items_and_tools_are_rejected(self) -> None:
        project_root, project_file, _package_root = CONTRACT.PROJECT_SPECS[10]
        project = self.root / project_root / project_file
        original = project.read_text(encoding="utf-8")
        cases = (
            ('<ItemGroup><Compile Include="/tmp/unbound.cs" /></ItemGroup>', "msbuild_item_path_untrusted"),
            ('<ItemGroup><Analyzer Include="/tmp/unbound.dll" /></ItemGroup>', "msbuild_item_untrusted"),
            ('<ItemGroup><ProjectReference Include="/tmp/unbound.csproj" /></ItemGroup>', "msbuild_project_reference_untrusted"),
            ('<UsingTask TaskName="Unbound" AssemblyFile="/tmp/unbound.dll" />', "msbuild_definition_untrusted"),
            ('<Target Name="Unbound"><Exec Command="/tmp/unbound" /></Target>', "msbuild_target_untrusted"),
        )
        for injected, reason in cases:
            with self.subTest(reason=reason):
                project.write_text(
                    original.replace("</Project>", f"{injected}</Project>"),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(CONTRACT.ProofContractError, reason):
                    CONTRACT._candidate_source_build_inputs(self.root)
        project.write_text(original, encoding="utf-8")

    def test_msbuild_item_lists_expressions_conditions_and_media_fallback_are_rejected(self) -> None:
        project_root, project_file, _package_root = CONTRACT.PROJECT_SPECS[10]
        project = self.root / project_root / project_file
        original = project.read_text(encoding="utf-8")
        cases = (
            ('<ItemGroup><Compile Include="Source.cs;/tmp/unbound.cs" /></ItemGroup>', "msbuild_item_path_untrusted"),
            ('<ItemGroup><Compile Include="@(UnboundCompile)" /></ItemGroup>', "msbuild_item_path_untrusted"),
            (
                '<PropertyGroup Condition="Exists(\'/tmp/unbound.props\')"><Description>unsafe</Description></PropertyGroup>',
                "msbuild_condition_untrusted",
            ),
            (
                '<PropertyGroup><Description>$([System.IO.File]::ReadAllText(\'/tmp/unbound.txt\'))</Description></PropertyGroup>',
                "msbuild_property_expression_untrusted",
            ),
            (
                '<PropertyGroup><PreferBundledChummerMediaContracts>true</PreferBundledChummerMediaContracts></PropertyGroup>',
                "msbuild_property_value_untrusted",
            ),
        )
        for injected, reason in cases:
            with self.subTest(reason=reason):
                project.write_text(
                    original.replace("</Project>", f"{injected}</Project>"),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(CONTRACT.ProofContractError, reason):
                    CONTRACT._candidate_source_build_inputs(self.root)
        project.write_text(original, encoding="utf-8")

    def test_project_assets_external_project_and_asset_paths_are_rejected(self) -> None:
        project_root, project_file, _package_root = CONTRACT.PROJECT_SPECS[10]
        assets_path = self.root / project_root / "obj" / "project.assets.json"
        original = json.loads(assets_path.read_text(encoding="utf-8"))

        external_project = json.loads(json.dumps(original))
        external_project["libraries"]["Unbound.Project/1.0.0"] = {
            "type": "project",
            "path": "/tmp/unbound.csproj",
            "msbuildProject": "/tmp/unbound.csproj",
        }
        assets_path.write_text(json.dumps(external_project, separators=(",", ":")) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "project_assets_project_path_untrusted"):
            CONTRACT._candidate_source_build_inputs(self.root)

        external_asset = json.loads(json.dumps(original))
        external_asset["targets"][".NETCoreApp,Version=v10.0"]["fake.package/1.0.0"] = {
            "type": "package",
            "compile": {"../../../../tmp/unbound.dll": {}},
        }
        assets_path.write_text(json.dumps(external_asset, separators=(",", ":")) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "project_assets_target_asset_path_invalid"):
            CONTRACT._candidate_source_build_inputs(self.root)

        assets_path.write_text(json.dumps(original, separators=(",", ":")) + "\n", encoding="utf-8")

    def test_msbuild_response_file_is_rejected(self) -> None:
        project_root, _project_file, _package_root = CONTRACT.PROJECT_SPECS[10]
        response_file = self.root / project_root / "Directory.Build.rsp"
        response_file.write_text("-p:OutputPath=/tmp/unbound-output\n", encoding="utf-8")
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "msbuild_response_file_untrusted"):
            CONTRACT._candidate_source_build_inputs(self.root)

    def test_symlink_hidden_under_excluded_output_directory_is_rejected(self) -> None:
        project_root, _project_file, _package_root = CONTRACT.PROJECT_SPECS[10]
        output_directory = self.root / project_root / "bin" / "Debug"
        output_directory.mkdir(parents=True)
        (output_directory / "linked-source.cs").symlink_to(self.root / project_root / "Source.cs")
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "candidate_project_tree_symlink"):
            CONTRACT._candidate_source_build_inputs(self.root)

    def test_proof_mode_solution_lane_is_forced_off(self) -> None:
        result = subprocess.run(
            [
                "/usr/bin/bash",
                "--noprofile",
                "--norc",
                str(self.root / CONTRACT.CLEANROOM_BUILDER_PATH),
            ],
            cwd=self.root,
            env={
                **os.environ,
                "CHUMMER_BUILD_NO_RESTORE": "1",
                "CHUMMER_BUILD_SOLUTION": "1",
                "PATH": "/usr/bin:/bin",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("forbid the unbound solution lane", result.stderr)

    def test_in_run_source_staged_and_managed_drift_fail_closed(self) -> None:
        self.executor.drift_source_path = self.root / "Chummer.Run.Api" / "Source.cs"
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "staged_candidate_source_mismatch"):
            self.run_owned()
        self.assert_running_failure("staged_candidate_source_mismatch")

        self.executor.drift_source_path = None
        source = self.root / "Chummer.Run.Api" / "Source.cs"
        source.write_text("namespace Smoke.Chummer_Run_Api_csproj;\n", encoding="utf-8")
        self.executor.drift_staged = True
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "staged_candidate_source_mismatch"):
            self.run_owned()
        self.assert_running_failure("staged_candidate_source_mismatch")

        self.executor.drift_staged = False
        self.executor.drift_managed_path = self.csc
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "managed_dotnet_closure_drift"):
            self.run_owned()
        self.assert_running_failure("managed_dotnet_closure_drift")

    def test_canonical_output_rejects_symlink_ancestor(self) -> None:
        published = self.root / ".codex-studio" / "published"
        published.rmdir()
        target = self.workspace / "redirected"
        target.mkdir()
        published.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(CONTRACT.ProofContractError, "receipt_output_symlink_ancestor"):
            self.run_owned()

    def test_legacy_running_duplicate_oversize_and_weakened_policy_fail(self) -> None:
        self.write_payload({
            "contract_name": CONTRACT.CONTRACT_NAME,
            "status": "passed",
            "proof_kind": "source_backed_local_smoke_contract",
        })
        self.assertEqual(self.validate().reason_code, "contract_version_mismatch")

        self.run_owned()
        payload = self.payload()
        payload["status"] = "running"
        self.write_payload(payload)
        self.assertEqual(self.validate().reason_code, "status_mismatch")

        self.run_owned()
        raw = self.receipt.read_text(encoding="utf-8")
        self.receipt.write_text(
            raw.replace('  "status": "passed",', '  "status": "passed",\n  "status": "passed",', 1),
            encoding="utf-8",
        )
        self.assertEqual(self.validate().reason_code, "receipt_duplicate_key")

        self.receipt.write_bytes(b"{" + b" " * CONTRACT.MAX_RECEIPT_BYTES + b"}")
        self.assertEqual(self.validate().reason_code, "receipt_too_large")

        self.run_owned()
        self.assertEqual(
            self.validate(max_age_seconds=CONTRACT.DEFAULT_MAX_AGE_SECONDS + 1).reason_code,
            "max_age_policy_weakened",
        )
        self.assertEqual(
            self.validate(future_skew_seconds=CONTRACT.DEFAULT_FUTURE_SKEW_SECONDS + 1).reason_code,
            "future_skew_policy_weakened",
        )

    def test_future_stale_and_timestamp_overflow_fail_stably(self) -> None:
        self.run_owned()
        payload = self.payload()
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        future = now + dt.timedelta(hours=1)
        payload["started_at"] = CONTRACT.format_utc(future)
        payload["completed_at"] = CONTRACT.format_utc(future)
        payload["generated_at"] = CONTRACT.format_utc(future)
        payload["expires_at"] = CONTRACT.format_utc(future + CONTRACT.RECEIPT_LIFETIME)
        self.write_payload(payload)
        self.assertEqual(self.validate().reason_code, "receipt_from_future")

        old = now - dt.timedelta(hours=2)
        payload["started_at"] = CONTRACT.format_utc(old)
        payload["completed_at"] = CONTRACT.format_utc(old)
        payload["generated_at"] = CONTRACT.format_utc(old)
        payload["expires_at"] = CONTRACT.format_utc(old + CONTRACT.RECEIPT_LIFETIME)
        self.write_payload(payload)
        self.assertEqual(self.validate(max_age_seconds=60).reason_code, "receipt_too_old")

        payload["started_at"] = "9999-12-31T23:59:59Z"
        payload["completed_at"] = "9999-12-31T23:59:59Z"
        payload["generated_at"] = "9999-12-31T23:59:59Z"
        payload["expires_at"] = "9999-12-31T23:59:59Z"
        self.write_payload(payload)
        self.assertEqual(self.validate().reason_code, "timestamp_overflow")

    def test_manifest_tool_size_and_checkpoint_semantic_binding(self) -> None:
        self.run_owned()
        payload = self.payload()
        before = payload["execution"]["runtime_manifest_before"]
        after = payload["execution"]["runtime_manifest_after"]
        for manifest in (before, after):
            tool = next(item for item in manifest["entries"] if item["path"] == "toolchain/dotnet")
            tool["size_bytes"] += 1
            manifest["manifest_sha256"] = CONTRACT._manifest_hash(manifest["entries"])
        self.write_payload(payload)
        self.assertEqual(self.validate().reason_code, "toolchain_manifest_mismatch")

        self.run_owned()
        payload = self.payload()
        payload["execution"]["checkpoint_log"]["size_bytes"] += 1
        self.write_payload(payload)
        self.assertEqual(self.validate().reason_code, "checkpoint_log_semantic_mismatch")

    def test_real_source_spec_and_all_durable_inputs_are_valid(self) -> None:
        inputs = CONTRACT._repo_inputs(REPO_ROOT, CONTRACT.DOTNET_HOST_PATH, csc_path=None)
        self.assertEqual(tuple(inputs), CONTRACT.INPUT_FIELDS)
        self.assertEqual(inputs["journey_spec"]["version"], 1)

    def test_shell_program_and_prepare_helper_are_fixed(self) -> None:
        wrapper = (REPO_ROOT / CONTRACT.RUNNER_PATH).read_text(encoding="utf-8")
        self.assertIn("exec /usr/bin/python3 -I -S", wrapper)
        self.assertNotIn("PYTHON_BIN", wrapper)
        self.assertNotIn("CHUMMER_SKIP_CLEANROOM_BUILD", wrapper)
        self.assertNotIn("CHUMMER_CAMPAIGN_OS_LOCAL_PROOF_OUT", wrapper)
        self.assertNotIn("CHUMMER_VERIFY_RELEASE_PROOF_MAX_AGE_SECONDS", wrapper)

        helper = (REPO_ROOT / CONTRACT.PREPARE_HELPER_PATH).read_text(encoding="utf-8")
        self.assertIn("export PATH=/usr/bin:/bin", helper)
        self.assertNotIn("TEST_BIN", helper)
        self.assertIn("missing required primary smoke source", helper)
        self.assertIn("CHUMMER_BUILD_NO_RESTORE", helper)
        self.assertIn("Chummer.World.Contracts", helper)
        self.assertIn("producer-selected reference directories are outside the exact .NET 10 pack roots", helper)
        self.assertIn("/usr/bin/realpath -m -s", helper)
        self.assertIn("dir_fd=directory_fd", helper)
        self.assertIn("os.O_NOFOLLOW", helper)
        self.assertIn("os.O_EXCL", helper)
        self.assertNotIn('dotnet "$OUT_DLL"', helper)

        builder = (REPO_ROOT / CONTRACT.CLEANROOM_BUILDER_PATH).read_text(encoding="utf-8")
        self.assertIn("--no-restore", builder)
        self.assertIn("--no-incremental", builder)
        self.assertIn("-t:Rebuild", builder)
        self.assertIn("-p:BuildProjectReferences=false", builder)
        self.assertNotIn("-p:OutputPath=", builder)
        self.assertIn('CHUMMER_BUILD_SOLUTION:-0}', builder)
        self.assertIn("proof-mode cleanroom builds forbid the unbound solution lane", builder)
        self.assertIn("/usr/bin/dotnet build", builder)

        program = (REPO_ROOT / CONTRACT.SOURCE_PATH).read_text(encoding="utf-8")
        self.assertNotIn("EmitCampaignOsRuntimeCheckpoints", program)
        self.assertIn("CampaignOsRuntimeCheckpointTracker", program)
        self.assertIn("campaignProof.RequireAllCompleted()", program)
        self.assertIn("CHUMMER_CAMPAIGN_OS_CANDIDATE_ROOT", program)
        self.assertIn('CHUMMER_PUBLIC_STRICT_CONFIGURED_ROOT"] = "true"', program)
        self.assertIn('CheckpointSuffix = ".run_services_smoke_exit_zero"', program)
        for journey_id in CONTRACT.JOURNEY_IDS:
            self.assertIn(f'campaignProof.Complete("{journey_id}")', program)

        verification = (REPO_ROOT / "scripts" / "ai" / "run_services_verification.sh").read_text(encoding="utf-8")
        self.assertNotIn("materialize_campaign_os_local_proof.py", verification)


if __name__ == "__main__":
    unittest.main()
