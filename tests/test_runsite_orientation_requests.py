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
SCRIPT = REPO_ROOT / "scripts" / "verify_runsite_orientation_requests.py"
MATERIALIZER = REPO_ROOT / "scripts" / "materialize_hub_local_release_proof.py"
SERVICE_FILE = REPO_ROOT / "Chummer.Run.Api/Services/RunsiteOrientationRequestComposerService.cs"
PACKAGE_ID = "next90-m110-hub-runsite-orientation-requests"
FRONTIER_ID = 1545739925
COMPLETION_ACTION = "verify_closed_package_only"
DO_NOT_REOPEN_REASON = (
    "M110 chummer6-hub runsite orientation requests are complete; future shards must verify "
    "the governed composition route, generated proof receipts, and queue/registry rows instead "
    "of reopening this package."
)
SOURCE_FILES = [
    "Chummer.Run.Api/Services/RunsiteOrientationRequestComposerService.cs",
    "Chummer.Run.Api/Controllers/InternalRunsiteOrientationController.cs",
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
    "Chummer.Tests/RunsiteOrientationRequestComposerServiceTests.cs",
    "scripts/materialize_hub_local_release_proof.py",
    "scripts/verify_runsite_orientation_requests.py",
    "scripts/ai/verify.sh",
    "tests/test_hub_local_release_proof_native_support_route.py",
    "tests/test_runsite_orientation_requests.py",
]


class RunsiteOrientationRequestsProofTests(unittest.TestCase):
    @staticmethod
    def build_standalone_composer_project(project_path: Path) -> None:
        project_path.write_text(
            "\n".join(
                [
                    "<Project Sdk=\"Microsoft.NET.Sdk\">",
                    "  <PropertyGroup>",
                    "    <OutputType>Exe</OutputType>",
                    "    <TargetFramework>net10.0</TargetFramework>",
                    "    <ImplicitUsings>enable</ImplicitUsings>",
                    "    <Nullable>enable</Nullable>",
                    "  </PropertyGroup>",
                    "  <ItemGroup>",
                    f"    <Compile Include=\"{SERVICE_FILE.as_posix()}\" Link=\"RunsiteOrientationRequestComposerService.cs\" />",
                    "  </ItemGroup>",
                    "</Project>",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def test_verifier_accepts_repo_local_runsite_orientation_request_slice(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-accepts-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            verifier_paths = self.prepare_closed_verifier_inputs(temp_root)
            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("runsite orientation request proof passed", result.stdout)

    def test_verifier_fails_when_preview_safe_truth_posture_guard_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            service_path = temp_root / "Chummer.Run.Api/Services/RunsiteOrientationRequestComposerService.cs"
            service_text = service_path.read_text(encoding="utf-8")
            service_path.write_text(
                service_text.replace(
                    'public const string PreviewTruthPosture = "pre-session-orientation-only-not-tactical-truth";',
                    'public const string PreviewTruthPosture = "preview-truth-removed";',
                ),
                encoding="utf-8",
            )

            verifier_paths = self.prepare_closed_verifier_inputs(temp_root)
            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pre-session-orientation-only-not-tactical-truth", result.stderr)

    def test_verifier_fails_when_route_summary_launch_surface_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-route-summary-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            service_path = temp_root / "Chummer.Run.Api/Services/RunsiteOrientationRequestComposerService.cs"
            service_text = service_path.read_text(encoding="utf-8")
            service_path.write_text(
                service_text.replace(
                    "approved runsite pack '{pack.SourcePackId}' must not pre-compose route previews; route_summary:artifact_launch stays governed by the route summary.",
                    "approved runsite pack '{pack.SourcePackId}' must not pre-compose route previews.",
                ),
                encoding="utf-8",
            )

            verifier_paths = self.prepare_closed_verifier_inputs(temp_root)
            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("route_summary:artifact_launch", result.stderr)

    def test_verifier_fails_when_internal_request_endpoint_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-endpoint-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            controller_path = temp_root / "Chummer.Run.Api/Controllers/InternalRunsiteOrientationController.cs"
            controller_text = controller_path.read_text(encoding="utf-8")
            controller_path.write_text(
                controller_text.replace(
                    '[HttpPost("/api/internal/runsite-orientation/requests")]',
                    '[HttpPost("/api/internal/runsite-orientation/request-removed")]',
                ),
                encoding="utf-8",
            )

            verifier_paths = self.prepare_closed_verifier_inputs(temp_root)
            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[HttpPost("/api/internal/runsite-orientation/requests")]', result.stderr)

    def test_verifier_fails_when_service_registration_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-registration-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            registration_path = temp_root / "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs"
            registration_text = registration_path.read_text(encoding="utf-8")
            registration_path.write_text(
                registration_text.replace("        services.AddSingleton<RunsiteOrientationRequestComposerService>();\n", ""),
                encoding="utf-8",
            )

            verifier_paths = self.prepare_closed_verifier_inputs(temp_root)
            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RunsiteOrientationRequestComposerService", result.stderr)

    def test_verifier_fails_when_queue_work_task_id_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-queue-row-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            verifier_paths = self.prepare_closed_verifier_inputs(temp_root)
            queue_path = temp_root / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            queue_payload = self.build_closed_queue_payload()
            item = queue_payload["items"][0]
            item["work_task_id"] = "110.queue-drift"
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(
                temp_root,
                queue_staging_path=queue_path,
                design_queue_staging_path=verifier_paths["design_queue_staging_path"],
                successor_registry_path=verifier_paths["successor_registry_path"],
                local_release_proof_path=verifier_paths["local_release_proof_path"],
                served_release_proof_path=verifier_paths["served_release_proof_path"],
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("work_task_id 110.1", result.stderr)

    def test_verifier_fails_when_queue_frontier_id_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-queue-frontier-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            verifier_paths = self.prepare_closed_verifier_inputs(temp_root)
            queue_path = temp_root / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            queue_payload = self.build_closed_queue_payload()
            queue_payload["items"][0].pop("frontier_id", None)
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(
                temp_root,
                queue_staging_path=queue_path,
                design_queue_staging_path=verifier_paths["design_queue_staging_path"],
                successor_registry_path=verifier_paths["successor_registry_path"],
                local_release_proof_path=verifier_paths["local_release_proof_path"],
                served_release_proof_path=verifier_paths["served_release_proof_path"],
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("frontier_id must be 1545739925", result.stderr)

    def test_verifier_fails_when_queue_reopen_reason_is_weakened(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-queue-reopen-reason-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            verifier_paths = self.prepare_closed_verifier_inputs(temp_root)
            queue_path = temp_root / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
            queue_payload = self.build_closed_queue_payload()
            queue_payload["items"][0]["do_not_reopen_reason"] = "Reopen whenever the package looks stale."
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")

            result = self.run_verifier(
                temp_root,
                queue_staging_path=queue_path,
                design_queue_staging_path=verifier_paths["design_queue_staging_path"],
                successor_registry_path=verifier_paths["successor_registry_path"],
                local_release_proof_path=verifier_paths["local_release_proof_path"],
                served_release_proof_path=verifier_paths["served_release_proof_path"],
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("do_not_reopen_reason must be the package-specific closure note", result.stderr)

    def test_ai_verify_script_runs_runsite_orientation_proof(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/verify_runsite_orientation_requests.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_runsite_orientation_requests.py", verify_script)
        self.assertIn(
            "dotnet test Chummer.Tests/Chummer.Tests.csproj --filter RunsiteOrientationRequestComposerServiceTests --no-restore",
            verify_script,
        )

    def test_verifier_fails_when_repo_native_xunit_proof_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-xunit-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            xunit_path = temp_root / "Chummer.Tests/RunsiteOrientationRequestComposerServiceTests.cs"
            xunit_text = xunit_path.read_text(encoding="utf-8")
            xunit_path.write_text(
                xunit_text.replace(
                    "InternalControllerReturnsComposedOrientationRequestWhenAuthorized",
                    "InternalControllerReturnsComposedOrientationRequestRemoved",
                ),
                encoding="utf-8",
            )

            verifier_paths = self.prepare_closed_verifier_inputs(temp_root)
            result = self.run_verifier(temp_root, **verifier_paths)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("InternalControllerReturnsComposedOrientationRequestWhenAuthorized", result.stderr)

    def test_composer_builds_governed_runsite_bundle_request(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-compose-") as temp_dir:
            temp_root = Path(temp_dir)
            project_path = temp_root / "RunsiteOrientationComposerHarness.csproj"
            program_path = temp_root / "Program.cs"
            output_path = temp_root / "result.json"

            self.build_standalone_composer_project(project_path)
            program_path.write_text(
                "\n".join(
                    [
                        "using System.IO;",
                        "using System.Text.Json;",
                        "using Chummer.Run.Api.Services;",
                        "",
                        "RunsiteOrientationRequestComposerService service = new();",
                        "RunsiteOrientationRequestCompositionResult result = service.Compose(",
                        "    new RunsiteOrientationRequestComposeRequest(",
                        "        RequestedBy: \"campaign.ops\",",
                        "        BundleId: \"runsite-redmond-bundle\",",
                        "        RunsitePack: new ApprovedRunsiteOrientationPack(",
                        "            SourcePackId: \"runsite-pack-redmond\",",
                        "            ApprovalState: \"approved\",",
                        "            ProvenanceRef: \"runsite:redmond-docks:orientation:v1\",",
                        "            EvidenceRefs: new[]",
                        "            {",
                        "                \"runsite:redmond-docks\",",
                        "                \"route-summary:redmond-docks-route\",",
                        "                \"preview-safe:pre-session\",",
                        "                \"pre-session:approved\"",
                        "            },",
                        "            RouteSummaryId: \"redmond-docks-route\",",
                        "            ArtifactTemplates: new[]",
                        "            {",
                        "                new RunsiteOrientationArtifactTemplate(",
                        "                    TemplateId: \"host-intro\",",
                        "                    Role: RunsiteOrientationArtifactRole.HostClip,",
                        "                    Category: \"runsite/orientation/host-clip\",",
                        "                    Payload: \"{\\\"script\\\":\\\"Stay on the marked lane.\\\"}\",",
                        "                    OutputFormat: \"mp4\",",
                        "                    RouteSegmentId: \"segment-a\",",
                        "                    DeduplicationKey: \"host-intro\"),",
                        "                new RunsiteOrientationArtifactTemplate(",
                        "                    TemplateId: \"tour-sibling\",",
                        "                    Role: RunsiteOrientationArtifactRole.TourSibling,",
                        "                    Category: \"runsite/orientation/tour\",",
                        "                    Payload: \"{\\\"tour\\\":\\\"catwalk\\\"}\",",
                        "                    OutputFormat: \"json\",",
                        "                    RouteSegmentId: \"segment-b\",",
                        "                    DeduplicationKey: \"tour-sibling\")",
                        "            },",
                        "            Audience: \"players,gm\",",
                        "            Locale: \"de-AT\"),",
                        "        RouteSummary: new RunsiteRouteSummary(",
                        "            RouteSummaryId: \"redmond-docks-route\",",
                        "            Segments: new[]",
                        "            {",
                        "                new RunsiteRouteSummarySegment(",
                        "                    RouteSegmentId: \"segment-a\",",
                        "                    InspectableTruthRef: \"/artifacts/routes/redmond-docks-route/segment-a\",",
                        "                    PreviewPayload: \"{\\\"frame\\\":\\\"alpha\\\"}\"),",
                        "                new RunsiteRouteSummarySegment(",
                        "                    RouteSegmentId: \"segment-b\",",
                        "                    InspectableTruthRef: \"/artifacts/routes/redmond-docks-route/segment-b\",",
                        "                    PreviewPayload: \"{\\\"frame\\\":\\\"beta\\\"}\")",
                        "            }),",
                        "        PreviewSafeTruth: new RunsitePreviewSafePreSessionTruth(",
                        "            PreviewTruthPosture: RunsiteOrientationRequestComposerService.PreviewTruthPosture,",
                        "            Summary: \"Inspectable route previews stay inspectable before session start.\",",
                        "            InspectableTruthRefs: new[]",
                        "            {",
                        "                \"/artifacts/routes/redmond-docks-route/segment-a\",",
                        "                \"/artifacts/routes/redmond-docks-route/segment-b\"",
                        "            }),",
                        "        Audience: \"players\",",
                        "        Locale: \"de-AT\",",
                        "        RequestedAtUtc: DateTimeOffset.Parse(\"2026-04-23T21:31:27Z\")));",
                        "",
                        f"File.WriteAllText(\"{output_path.as_posix()}\", JsonSerializer.Serialize(result));",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                ["dotnet", "run", "--project", str(project_path)],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual("chummer6-hub.runsite_orientation_request.v1", payload["ContractName"])
        self.assertEqual("players", payload["Audience"])
        self.assertEqual("de-AT", payload["Locale"])
        self.assertEqual("runsite-redmond-bundle", payload["BundleRequest"]["BundleId"])
        self.assertEqual("redmond-docks-route", payload["BundleRequest"]["RouteSummaryId"])
        self.assertEqual("2026-04-23T21:31:27+00:00", payload["BundleRequest"]["RequestedAtUtc"])
        self.assertEqual(
            ["segment-a", "segment-b"],
            [launch["RouteSegmentId"] for launch in payload["RouteSummaryArtifactLaunches"]],
        )
        self.assertTrue(
            all(launch["ApprovedRunsitePackId"] == "runsite-pack-redmond" for launch in payload["RouteSummaryArtifactLaunches"])
        )
        self.assertTrue(
            all(launch["RouteSummaryId"] == "redmond-docks-route" for launch in payload["RouteSummaryArtifactLaunches"])
        )
        self.assertTrue(
            all(
                launch["PreviewTruthPosture"] == "pre-session-orientation-only-not-tactical-truth"
                for launch in payload["RouteSummaryArtifactLaunches"]
            )
        )
        self.assertTrue(
            all(
                launch["PreviewSafeTruthSummary"] == "Inspectable route previews stay inspectable before session start."
                for launch in payload["RouteSummaryArtifactLaunches"]
            )
        )
        self.assertTrue(
            all(
                launch["PreviewSafeInspectableTruthRefs"]
                == [
                    "/artifacts/routes/redmond-docks-route/segment-a",
                    "/artifacts/routes/redmond-docks-route/segment-b",
                ]
                for launch in payload["RouteSummaryArtifactLaunches"]
            )
        )
        self.assertTrue(
            all(
                launch["EvidenceRefs"]
                == [
                    "pre-session:approved",
                    "preview-safe:pre-session",
                    "route-summary:redmond-docks-route",
                    "runsite:redmond-docks",
                ]
                for launch in payload["RouteSummaryArtifactLaunches"]
            )
        )
        self.assertTrue(all(launch["Audience"] == "players" for launch in payload["RouteSummaryArtifactLaunches"]))
        self.assertTrue(all(launch["Locale"] == "de-AT" for launch in payload["RouteSummaryArtifactLaunches"]))
        route_preview_artifacts = [
            artifact
            for artifact in payload["BundleRequest"]["Artifacts"]
            if artifact["Role"] == 1
        ]
        self.assertEqual(["segment-a", "segment-b"], [artifact["RouteSegmentId"] for artifact in route_preview_artifacts])
        self.assertTrue(
            all(artifact["DeduplicationKey"].startswith("runsite-orientation.") for artifact in route_preview_artifacts)
        )
        self.assertTrue(all(artifact["AllowPersistentPinning"] is False for artifact in route_preview_artifacts))
        host_clip = next(artifact for artifact in payload["BundleRequest"]["Artifacts"] if artifact["Role"] == 0)
        governed_payload = json.loads(host_clip["Payload"])
        self.assertEqual("runsite-pack-redmond", governed_payload["sourcePackId"])
        self.assertEqual("runsite:redmond-docks:orientation:v1", governed_payload["provenanceRef"])
        self.assertEqual("players", governed_payload["audience"])
        self.assertEqual("de-AT", governed_payload["locale"])
        self.assertEqual(
            [
                "pre-session:approved",
                "preview-safe:pre-session",
                "route-summary:redmond-docks-route",
                "runsite:redmond-docks",
            ],
            governed_payload["evidenceRefs"],
        )
        self.assertEqual(
            [
                "/artifacts/routes/redmond-docks-route/segment-a",
                "/artifacts/routes/redmond-docks-route/segment-b",
            ],
            governed_payload["previewSafeInspectableTruthRefs"],
        )
        self.assertEqual(
            "Inspectable route previews stay inspectable before session start.",
            governed_payload["previewSafeTruthSummary"],
        )
        self.assertEqual({"script": "Stay on the marked lane."}, governed_payload["payload"])

    def test_composer_rejects_missing_route_summary_evidence_anchor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-missing-route-summary-") as temp_dir:
            temp_root = Path(temp_dir)
            project_path = temp_root / "RunsiteOrientationComposerHarness.csproj"
            program_path = temp_root / "Program.cs"

            self.build_standalone_composer_project(project_path)
            program_path.write_text(
                "\n".join(
                    [
                        "using Chummer.Run.Api.Services;",
                        "",
                        "RunsiteOrientationRequestComposerService service = new();",
                        "service.Compose(",
                        "    new RunsiteOrientationRequestComposeRequest(",
                        "        RequestedBy: \"campaign.ops\",",
                        "        BundleId: \"runsite-redmond-bundle\",",
                        "        RunsitePack: new ApprovedRunsiteOrientationPack(",
                        "            SourcePackId: \"runsite-pack-redmond\",",
                        "            ApprovalState: \"approved\",",
                        "            ProvenanceRef: \"runsite:redmond-docks:orientation:v1\",",
                        "            EvidenceRefs: new[] { \"runsite:redmond-docks\", \"preview-safe:pre-session\", \"pre-session:approved\" },",
                        "            RouteSummaryId: \"redmond-docks-route\",",
                        "            ArtifactTemplates: new[]",
                        "            {",
                        "                new RunsiteOrientationArtifactTemplate(",
                        "                    TemplateId: \"host-intro\",",
                        "                    Role: RunsiteOrientationArtifactRole.HostClip,",
                        "                    Category: \"runsite/orientation/host-clip\",",
                        "                    Payload: \"{\\\"script\\\":\\\"Stay on the marked lane.\\\"}\",",
                        "                    OutputFormat: \"mp4\",",
                        "                    RouteSegmentId: \"segment-a\",",
                        "                    DeduplicationKey: \"host-intro\")",
                        "            }),",
                        "        RouteSummary: new RunsiteRouteSummary(",
                        "            RouteSummaryId: \"redmond-docks-route\",",
                        "            Segments: new[]",
                        "            {",
                        "                new RunsiteRouteSummarySegment(",
                        "                    RouteSegmentId: \"segment-a\",",
                        "                    InspectableTruthRef: \"/artifacts/routes/redmond-docks-route/segment-a\",",
                        "                    PreviewPayload: \"{\\\"frame\\\":\\\"alpha\\\"}\")",
                        "            }),",
                        "        PreviewSafeTruth: new RunsitePreviewSafePreSessionTruth(",
                        "            PreviewTruthPosture: RunsiteOrientationRequestComposerService.PreviewTruthPosture,",
                        "            Summary: \"Inspectable route previews stay inspectable before session start.\",",
                        "            InspectableTruthRefs: new[] { \"/artifacts/routes/redmond-docks-route/segment-a\" })));",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                ["dotnet", "run", "--project", str(project_path)],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("route-summary:redmond-docks-route", result.stderr or result.stdout)

    def test_composer_rejects_missing_preview_safe_evidence_anchor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-missing-preview-safe-") as temp_dir:
            temp_root = Path(temp_dir)
            project_path = temp_root / "RunsiteOrientationComposerHarness.csproj"
            program_path = temp_root / "Program.cs"

            self.build_standalone_composer_project(project_path)
            program_path.write_text(
                "\n".join(
                    [
                        "using Chummer.Run.Api.Services;",
                        "",
                        "RunsiteOrientationRequestComposerService service = new();",
                        "service.Compose(",
                        "    new RunsiteOrientationRequestComposeRequest(",
                        "        RequestedBy: \"campaign.ops\",",
                        "        BundleId: \"runsite-redmond-bundle\",",
                        "        RunsitePack: new ApprovedRunsiteOrientationPack(",
                        "            SourcePackId: \"runsite-pack-redmond\",",
                        "            ApprovalState: \"approved\",",
                        "            ProvenanceRef: \"runsite:redmond-docks:orientation:v1\",",
                        "            EvidenceRefs: new[] { \"runsite:redmond-docks\", \"route-summary:redmond-docks-route\", \"pre-session:approved\" },",
                        "            RouteSummaryId: \"redmond-docks-route\",",
                        "            ArtifactTemplates: new[]",
                        "            {",
                        "                new RunsiteOrientationArtifactTemplate(",
                        "                    TemplateId: \"host-intro\",",
                        "                    Role: RunsiteOrientationArtifactRole.HostClip,",
                        "                    Category: \"runsite/orientation/host-clip\",",
                        "                    Payload: \"{\\\"script\\\":\\\"Stay on the marked lane.\\\"}\",",
                        "                    OutputFormat: \"mp4\",",
                        "                    RouteSegmentId: \"segment-a\",",
                        "                    DeduplicationKey: \"host-intro\")",
                        "            }),",
                        "        RouteSummary: new RunsiteRouteSummary(",
                        "            RouteSummaryId: \"redmond-docks-route\",",
                        "            Segments: new[]",
                        "            {",
                        "                new RunsiteRouteSummarySegment(",
                        "                    RouteSegmentId: \"segment-a\",",
                        "                    InspectableTruthRef: \"/artifacts/routes/redmond-docks-route/segment-a\",",
                        "                    PreviewPayload: \"{\\\"frame\\\":\\\"alpha\\\"}\")",
                        "            }),",
                        "        PreviewSafeTruth: new RunsitePreviewSafePreSessionTruth(",
                        "            PreviewTruthPosture: RunsiteOrientationRequestComposerService.PreviewTruthPosture,",
                        "            Summary: \"Inspectable route previews stay inspectable before session start.\",",
                        "            InspectableTruthRefs: new[] { \"/artifacts/routes/redmond-docks-route/segment-a\" })));",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                ["dotnet", "run", "--project", str(project_path)],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("preview-safe:* anchor", result.stderr or result.stdout)

    def test_composer_rejects_invalid_json_payloads(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-invalid-json-") as temp_dir:
            temp_root = Path(temp_dir)
            project_path = temp_root / "RunsiteOrientationComposerHarness.csproj"
            program_path = temp_root / "Program.cs"

            self.build_standalone_composer_project(project_path)
            program_path.write_text(
                "\n".join(
                    [
                        "using Chummer.Run.Api.Services;",
                        "",
                        "RunsiteOrientationRequestComposerService service = new();",
                        "service.Compose(",
                        "    new RunsiteOrientationRequestComposeRequest(",
                        "        RequestedBy: \"campaign.ops\",",
                        "        BundleId: \"runsite-redmond-bundle\",",
                        "        RunsitePack: new ApprovedRunsiteOrientationPack(",
                        "            SourcePackId: \"runsite-pack-redmond\",",
                        "            ApprovalState: \"approved\",",
                        "            ProvenanceRef: \"runsite:redmond-docks:orientation:v1\",",
                        "            EvidenceRefs: new[] { \"runsite:redmond-docks\", \"route-summary:redmond-docks-route\", \"preview-safe:pre-session\", \"pre-session:approved\" },",
                        "            RouteSummaryId: \"redmond-docks-route\",",
                        "            ArtifactTemplates: new[]",
                        "            {",
                        "                new RunsiteOrientationArtifactTemplate(",
                        "                    TemplateId: \"host-intro\",",
                        "                    Role: RunsiteOrientationArtifactRole.HostClip,",
                        "                    Category: \"runsite/orientation/host-clip\",",
                        "                    Payload: \"{\\\"script\\\":}\",",
                        "                    OutputFormat: \"mp4\",",
                        "                    RouteSegmentId: \"segment-a\",",
                        "                    DeduplicationKey: \"host-intro\")",
                        "            }),",
                        "        RouteSummary: new RunsiteRouteSummary(",
                        "            RouteSummaryId: \"redmond-docks-route\",",
                        "            Segments: new[]",
                        "            {",
                        "                new RunsiteRouteSummarySegment(",
                        "                    RouteSegmentId: \"segment-a\",",
                        "                    InspectableTruthRef: \"/artifacts/routes/redmond-docks-route/segment-a\",",
                        "                    PreviewPayload: \"{\\\"frame\\\":\\\"alpha\\\"}\")",
                        "            }),",
                        "        PreviewSafeTruth: new RunsitePreviewSafePreSessionTruth(",
                        "            PreviewTruthPosture: RunsiteOrientationRequestComposerService.PreviewTruthPosture,",
                        "            Summary: \"Inspectable route previews stay inspectable before session start.\",",
                        "            InspectableTruthRefs: new[] { \"/artifacts/routes/redmond-docks-route/segment-a\" })));",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                ["dotnet", "run", "--project", str(project_path)],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("valid JSON-shaped preview-safe content", result.stderr or result.stdout)

    def test_composer_rejects_duplicate_deduplication_keys(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-duplicate-dedupe-") as temp_dir:
            temp_root = Path(temp_dir)
            project_path = temp_root / "RunsiteOrientationComposerHarness.csproj"
            program_path = temp_root / "Program.cs"

            self.build_standalone_composer_project(project_path)
            program_path.write_text(
                "\n".join(
                    [
                        "using Chummer.Run.Api.Services;",
                        "",
                        "RunsiteOrientationRequestComposerService service = new();",
                        "service.Compose(",
                        "    new RunsiteOrientationRequestComposeRequest(",
                        "        RequestedBy: \"campaign.ops\",",
                        "        BundleId: \"runsite-redmond-bundle\",",
                        "        RunsitePack: new ApprovedRunsiteOrientationPack(",
                        "            SourcePackId: \"runsite-pack-redmond\",",
                        "            ApprovalState: \"approved\",",
                        "            ProvenanceRef: \"runsite:redmond-docks:orientation:v1\",",
                        "            EvidenceRefs: new[] { \"runsite:redmond-docks\", \"route-summary:redmond-docks-route\", \"preview-safe:pre-session\", \"pre-session:approved\" },",
                        "            RouteSummaryId: \"redmond-docks-route\",",
                        "            ArtifactTemplates: new[]",
                        "            {",
                        "                new RunsiteOrientationArtifactTemplate(",
                        "                    TemplateId: \"host-intro-a\",",
                        "                    Role: RunsiteOrientationArtifactRole.HostClip,",
                        "                    Category: \"runsite/orientation/host-clip\",",
                        "                    Payload: \"{\\\"script\\\":\\\"Stay on the marked lane.\\\"}\",",
                        "                    OutputFormat: \"mp4\",",
                        "                    RouteSegmentId: \"segment-a\",",
                        "                    DeduplicationKey: \"host-intro\"),",
                        "                new RunsiteOrientationArtifactTemplate(",
                        "                    TemplateId: \"host-intro-b\",",
                        "                    Role: RunsiteOrientationArtifactRole.HostClip,",
                        "                    Category: \"runsite/orientation/host-clip\",",
                        "                    Payload: \"{\\\"script\\\":\\\"Do not split the party.\\\"}\",",
                        "                    OutputFormat: \"mp4\",",
                        "                    RouteSegmentId: \"segment-a\",",
                        "                    DeduplicationKey: \"host-intro\")",
                        "            },",
                        "            Audience: \"players,gm\",",
                        "            Locale: \"de-AT\"),",
                        "        RouteSummary: new RunsiteRouteSummary(",
                        "            RouteSummaryId: \"redmond-docks-route\",",
                        "            Segments: new[]",
                        "            {",
                        "                new RunsiteRouteSummarySegment(",
                        "                    RouteSegmentId: \"segment-a\",",
                        "                    InspectableTruthRef: \"/artifacts/routes/redmond-docks-route/segment-a\",",
                        "                    PreviewPayload: \"{\\\"frame\\\":\\\"alpha\\\"}\")",
                        "            }),",
                        "        PreviewSafeTruth: new RunsitePreviewSafePreSessionTruth(",
                        "            PreviewTruthPosture: RunsiteOrientationRequestComposerService.PreviewTruthPosture,",
                        "            Summary: \"Inspectable route previews stay inspectable before session start.\",",
                        "            InspectableTruthRefs: new[] { \"/artifacts/routes/redmond-docks-route/segment-a\" })));",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                ["dotnet", "run", "--project", str(project_path)],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must not emit duplicate deduplication key", result.stderr or result.stdout)

    def test_composer_rejects_route_summary_category_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-route-category-") as temp_dir:
            temp_root = Path(temp_dir)
            project_path = temp_root / "RunsiteOrientationComposerHarness.csproj"
            program_path = temp_root / "Program.cs"

            self.build_standalone_composer_project(project_path)
            program_path.write_text(
                "\n".join(
                    [
                        "using Chummer.Run.Api.Services;",
                        "",
                        "RunsiteOrientationRequestComposerService service = new();",
                        "service.Compose(",
                        "    new RunsiteOrientationRequestComposeRequest(",
                        "        RequestedBy: \"campaign.ops\",",
                        "        BundleId: \"runsite-redmond-bundle\",",
                        "        RunsitePack: new ApprovedRunsiteOrientationPack(",
                        "            SourcePackId: \"runsite-pack-redmond\",",
                        "            ApprovalState: \"approved\",",
                        "            ProvenanceRef: \"runsite:redmond-docks:orientation:v1\",",
                        "            EvidenceRefs: new[] { \"runsite:redmond-docks\", \"route-summary:redmond-docks-route\", \"preview-safe:pre-session\", \"pre-session:approved\" },",
                        "            RouteSummaryId: \"redmond-docks-route\",",
                        "            ArtifactTemplates: new[]",
                        "            {",
                        "                new RunsiteOrientationArtifactTemplate(",
                        "                    TemplateId: \"host-intro\",",
                        "                    Role: RunsiteOrientationArtifactRole.HostClip,",
                        "                    Category: \"runsite/orientation/host-clip\",",
                        "                    Payload: \"{\\\"script\\\":\\\"Stay on the marked lane.\\\"}\",",
                        "                    OutputFormat: \"mp4\",",
                        "                    RouteSegmentId: \"segment-a\",",
                        "                    DeduplicationKey: \"host-intro\")",
                        "            }),",
                        "        RouteSummary: new RunsiteRouteSummary(",
                        "            RouteSummaryId: \"redmond-docks-route\",",
                        "            Segments: new[]",
                        "            {",
                        "                new RunsiteRouteSummarySegment(",
                        "                    RouteSegmentId: \"segment-a\",",
                        "                    InspectableTruthRef: \"/artifacts/routes/redmond-docks-route/segment-a\",",
                        "                    PreviewPayload: \"{\\\"frame\\\":\\\"alpha\\\"}\",",
                        "                    Category: \"runsite/orientation/host-clip\")",
                        "            }),",
                        "        PreviewSafeTruth: new RunsitePreviewSafePreSessionTruth(",
                        "            PreviewTruthPosture: RunsiteOrientationRequestComposerService.PreviewTruthPosture,",
                        "            Summary: \"Inspectable route previews stay inspectable before session start.\",",
                        "            InspectableTruthRefs: new[] { \"/artifacts/routes/redmond-docks-route/segment-a\" })));",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                ["dotnet", "run", "--project", str(project_path)],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("route_summary:artifact_launch remains route-summary governed", result.stderr or result.stdout)

    def test_materialized_release_proof_includes_runsite_orientation_package(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runsite-orientation-release-proof-") as temp_dir:
            proof_path = Path(temp_dir) / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            result = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    str(proof_path),
                    "https://chummer.run",
                    "docker-compose.yml",
                    "120",
                    "true",
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(proof_path.read_text(encoding="utf-8"))

        package = payload["successor_queue_packages_by_id"]["next90-m110-hub-runsite-orientation-requests"]
        self.assertEqual(110, package["milestone_id"])
        self.assertEqual(1545739925, package["frontier_id"])
        self.assertEqual("complete", package["status"])
        self.assertEqual("verify_closed_package_only", package["completion_action"])
        self.assertEqual(
            ["runsite_orientation_requests", "route_summary:artifact_launch"],
            package["owned_surfaces"],
        )

        receipts = {
            receipt["receipt_id"]: receipt
            for receipt in payload["proof_receipts"]
            if receipt.get("package_id") == "next90-m110-hub-runsite-orientation-requests"
        }
        self.assertIn("runsite_orientation_requests", receipts)
        self.assertIn("route_summary:artifact_launch", receipts)
        self.assertEqual(
            ["/api/internal/runsite-orientation/requests", "/artifacts/routes/{routeSummaryId}/{routeSegmentId}"],
            receipts["runsite_orientation_requests"]["routes"],
        )
        self.assertEqual(
            ["route_summary:artifact_launch", "route_preview:inspectable_truth", "runsite_orientation_bundle"],
            receipts["route_summary:artifact_launch"]["surfaces"],
        )

    def copy_sources(self, temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def build_closed_queue_payload(self) -> dict[str, object]:
        return {
            "items": [
                {
                    "title": "Compose runsite orientation requests from approved runsite packs and route summaries",
                    "task": "Compose governed runsite orientation requests from approved runsite packs, route summaries, and preview-safe pre-session truth.",
                    "package_id": PACKAGE_ID,
                    "work_task_id": "110.1",
                    "milestone_id": 110,
                    "wave": "W10",
                    "frontier_id": FRONTIER_ID,
                    "repo": "chummer6-hub",
                    "status": "complete",
                    "completion_action": COMPLETION_ACTION,
                    "do_not_reopen_reason": DO_NOT_REOPEN_REASON,
                    "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
                    "owned_surfaces": ["runsite_orientation_requests", "route_summary:artifact_launch"],
                }
            ]
        }

    def build_closed_registry_payload(self) -> dict[str, object]:
        return {
            "milestones": [
                {
                    "id": 110,
                    "work_tasks": [
                        {
                            "id": "110.1",
                            "owner": "chummer6-hub",
                            "title": "Compose runsite orientation requests from approved runsite packs and route summaries.",
                            "status": "complete",
                            "evidence": [
                                "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Services/RunsiteOrientationRequestComposerService.cs",
                                "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/Controllers/InternalRunsiteOrientationController.cs",
                                "/docker/chummercomplete/chummer.run-services/scripts/verify_runsite_orientation_requests.py",
                                "/docker/chummercomplete/chummer.run-services/tests/test_runsite_orientation_requests.py",
                                "/docker/chummercomplete/chummer.run-services/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
                                "dotnet test Chummer.Tests/Chummer.Tests.csproj --filter RunsiteOrientationRequestComposerServiceTests --no-restore exits 0.",
                                "python3 -m unittest tests/test_runsite_orientation_requests.py exits 0.",
                                "./scripts/ai/verify.sh exits 0.",
                            ],
                        }
                    ],
                }
            ]
        }

    def prepare_closed_verifier_inputs(self, temp_root: Path) -> dict[str, Path]:
        queue_staging_path = temp_root / "NEXT_90_DAY_QUEUE_STAGING.generated.yaml"
        design_queue_staging_path = temp_root / "NEXT_90_DAY_QUEUE_STAGING.design.generated.yaml"
        successor_registry_path = temp_root / "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml"
        local_release_proof_path = temp_root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
        served_release_proof_path = temp_root / "HUB_LOCAL_RELEASE_PROOF.served.generated.json"

        queue_payload = self.build_closed_queue_payload()
        queue_staging_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")
        design_queue_staging_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")
        successor_registry_path.write_text(
            yaml.safe_dump(self.build_closed_registry_payload(), sort_keys=False),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                "python3",
                str(temp_root / "scripts" / "materialize_hub_local_release_proof.py"),
                str(local_release_proof_path),
                "https://chummer.run",
                "docker-compose.yml",
                "120",
                "true",
            ],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        shutil.copyfile(local_release_proof_path, served_release_proof_path)

        return {
            "queue_staging_path": queue_staging_path,
            "design_queue_staging_path": design_queue_staging_path,
            "successor_registry_path": successor_registry_path,
            "local_release_proof_path": local_release_proof_path,
            "served_release_proof_path": served_release_proof_path,
        }

    def run_verifier(
        self,
        temp_root: Path,
        *,
        queue_staging_path: Path | None = None,
        design_queue_staging_path: Path | None = None,
        successor_registry_path: Path | None = None,
        local_release_proof_path: Path | None = None,
        served_release_proof_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_RUNSITE_ORIENTATION_ROOT"] = str(temp_root)
        if queue_staging_path is not None:
            env["CHUMMER_RUNSITE_ORIENTATION_QUEUE_STAGING"] = str(queue_staging_path)
        if design_queue_staging_path is not None:
            env["CHUMMER_RUNSITE_ORIENTATION_DESIGN_QUEUE_STAGING"] = str(design_queue_staging_path)
        if successor_registry_path is not None:
            env["CHUMMER_RUNSITE_ORIENTATION_SUCCESSOR_REGISTRY"] = str(successor_registry_path)
        env["CHUMMER_RUNSITE_ORIENTATION_LOCAL_RELEASE_PROOF"] = str(
            local_release_proof_path
            or (REPO_ROOT / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json")
        )
        env["CHUMMER_RUNSITE_ORIENTATION_SERVED_RELEASE_PROOF"] = str(
            served_release_proof_path
            or (
                REPO_ROOT
                / "Chummer.Run.Api"
                / "wwwroot"
                / "proofs"
                / "mac-codex-release"
                / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            )
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
