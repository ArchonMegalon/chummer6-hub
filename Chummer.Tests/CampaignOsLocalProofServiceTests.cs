using System.Diagnostics;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignOsLocalProofServiceTests
{
    private static readonly string[] JourneyIds =
    [
        "install_claim_restore_continue",
        "build_explain_publish",
        "campaign_session_recover_recap",
        "recover_from_sync_conflict",
        "report_cluster_release_notify",
        "organize_community_and_close_loop"
    ];

    [Fact]
    public void EvaluateAcceptsExactFreshV3ReceiptBoundToCurrentClosures()
    {
        using var fixture = new ProofFixture();
        fixture.WriteValidProof();

        var evaluation = fixture.CreateService().Evaluate();

        Assert.True(evaluation.IsValid, evaluation.ReasonCode);
        Assert.Equal("proof_valid", evaluation.ReasonCode);
        var proof = Assert.IsType<CampaignOsLocalProofSnapshot>(evaluation.Snapshot);
        Assert.Equal(3, proof.ContractVersion);
        Assert.Equal("passed", proof.Status);
        Assert.Equal(JourneyIds, proof.JourneysPassed);
    }

    [Fact]
    public void EvaluateRejectsV2Receipt()
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        payload["contract_version"] = 2;
        fixture.WriteProof(payload);

        Assert.Equal("proof_contract_mismatch", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsWrongDependencyMode()
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        payload["invocation"]!["dependency_mode"] = "ambient_restore_allowed";
        fixture.WriteProof(payload);

        Assert.Equal("proof_invocation_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Theory]
    [InlineData("root")]
    [InlineData("invocation")]
    [InlineData("inputs")]
    [InlineData("execution")]
    public void EvaluateRejectsReorderedFrozenSchema(string section)
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        if (section == "root")
        {
            payload = ReorderFirstTwo(payload);
        }
        else
        {
            payload[section] = ReorderFirstTwo(payload[section]!.AsObject());
        }

        fixture.WriteProof(payload);
        Assert.False(fixture.CreateService().Evaluate().IsValid);
    }

    [Theory]
    [InlineData("candidate_source_build_inputs_after")]
    [InlineData("staged_candidate_inputs_after")]
    [InlineData("managed_dotnet_closure_after")]
    public void EvaluateRejectsExtraClosureField(string closureName)
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        payload["execution"]![closureName]!.AsObject()["unexpected"] = true;
        fixture.WriteProof(payload);

        Assert.Equal("proof_execution_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsDuplicateProperty()
    {
        using var fixture = new ProofFixture();
        var json = fixture.Serialize(fixture.CreateValidPayload());
        const string contract = "\"contract_name\":\"chummer6-hub.campaign_os_local_proof\"";
        fixture.WriteRaw(json.Replace(contract, contract + "," + contract, StringComparison.Ordinal));

        Assert.Equal("proof_duplicate_property", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsMalformedAndOversizedReceipts()
    {
        using var malformed = new ProofFixture();
        malformed.WriteRaw("{not-json");
        Assert.Equal("proof_json_invalid", malformed.CreateService().Evaluate().ReasonCode);

        using var oversized = new ProofFixture();
        oversized.WriteRaw(new string(' ', 2 * 1024 * 1024 + 1));
        Assert.Equal("proof_too_large", oversized.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsProofSymlinkWhenSupported()
    {
        using var fixture = new ProofFixture();
        var target = Path.Combine(fixture.Root, "receipt-target.json");
        File.WriteAllText(target, fixture.Serialize(fixture.CreateValidPayload()), Encoding.UTF8);
        Directory.CreateDirectory(Path.GetDirectoryName(fixture.ProofPath)!);
        try
        {
            File.CreateSymbolicLink(fixture.ProofPath, target);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or PlatformNotSupportedException)
        {
            return;
        }

        Assert.Equal("proof_link_disallowed", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsSymlinkedCurrentInputWhenSupported()
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        var source = fixture.InputPath("tests/RunServicesSmoke/Program.cs");
        var target = Path.Combine(fixture.Root, "source-target.cs");
        File.Copy(source, target);
        File.Delete(source);
        try
        {
            File.CreateSymbolicLink(source, target);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or PlatformNotSupportedException)
        {
            return;
        }

        fixture.WriteProof(payload);
        Assert.Equal("proof_inputs_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsPostMintSourceDrift()
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        fixture.WriteInput("tests/RunServicesSmoke/Program.cs", "changed after mint\n");
        fixture.WriteProof(payload);

        Assert.Equal("proof_inputs_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Theory]
    [InlineData("project_roots", 0)]
    [InlineData("runtime_data_roots", 1)]
    public void EvaluateRejectsPostMintBuildOrCanonTreeDrift(string collection, int index)
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        fixture.DriftCurrentCandidateRecord(collection, index);
        fixture.WriteProof(payload);

        Assert.Equal("proof_execution_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Theory]
    [InlineData("project_assets")]
    [InlineData("generated_nuget_imports")]
    [InlineData("nuget_packages")]
    [InlineData("ancestor_build_controls")]
    public void EvaluateRejectsPostMintAssetsImportsPackageOrAncestorDrift(string record)
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        fixture.DriftCurrentCandidateRecord(record);
        fixture.WriteProof(payload);

        Assert.Equal("proof_execution_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(5)]
    public void EvaluateRejectsPostMintFrameworkOrSdkDrift(int componentIndex)
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        fixture.DriftCurrentManagedComponent(componentIndex);
        fixture.WriteProof(payload);

        Assert.Equal("proof_execution_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsCandidateBeforeAfterDriftEvenWhenBothDigestsAreValid()
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        var after = payload["execution"]!["candidate_source_build_inputs_after"]!.AsObject();
        MutateTreeRecord(after["project_roots"]![0]!.AsObject());
        RefreshClosureDigest(after);
        fixture.WriteProof(payload);

        Assert.Equal("proof_execution_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsStagedClosureNotEqualToCandidateProjection()
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        foreach (var name in new[] { "staged_candidate_inputs_before", "staged_candidate_inputs_after" })
        {
            var staged = payload["execution"]![name]!.AsObject();
            MutateTreeRecord(staged["roots"]![0]!.AsObject());
            RefreshClosureDigest(staged);
        }

        fixture.WriteProof(payload);
        Assert.Equal("proof_execution_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsWrongClosureDigest()
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        payload["execution"]!["candidate_source_build_inputs_after"]!["closure_sha256"] = new string('0', 64);
        fixture.WriteProof(payload);

        Assert.Equal("proof_execution_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsWrongAssetAndImportCounts()
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        foreach (var name in new[] { "candidate_source_build_inputs_before", "candidate_source_build_inputs_after" })
        {
            var closure = payload["execution"]![name]!.AsObject();
            closure["project_assets"]!["file_count"] = 12;
            RefreshClosureDigest(closure);
        }

        fixture.WriteProof(payload);
        Assert.Equal("proof_execution_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsWrongPackageRootOrdering()
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        foreach (var name in new[] { "candidate_source_build_inputs_before", "candidate_source_build_inputs_after" })
        {
            var closure = payload["execution"]![name]!.AsObject();
            var roots = closure["nuget_package_roots"]!.AsArray();
            var first = roots[0]!.DeepClone();
            roots[0] = roots[1]!.DeepClone();
            roots[1] = first;
            RefreshClosureDigest(closure);
        }

        fixture.WriteProof(payload);
        Assert.Equal("proof_execution_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Theory]
    [InlineData("skipped")]
    [InlineData("failed")]
    public void EvaluateRejectsNonPassingRuntimeCheckpoint(string status)
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        payload["execution"]!["runtime_checkpoints"]![2]!["status"] = status;
        fixture.RefreshCheckpointLog(payload);
        fixture.WriteProof(payload);

        Assert.Equal("proof_execution_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsMissingRuntimeCheckpoint()
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        payload["execution"]!["runtime_checkpoints"]!.AsArray().RemoveAt(4);
        fixture.RefreshCheckpointLog(payload);
        fixture.WriteProof(payload);

        Assert.Equal("proof_execution_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsCheckpointFromAnotherRunEvenWithReboundLog()
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        payload["execution"]!["runtime_checkpoints"]![0]!["run_id"] = "6ba7b810-9dad-41d1-80b4-00c04fd430c8";
        fixture.RefreshCheckpointLog(payload);
        fixture.WriteProof(payload);

        Assert.Equal("proof_execution_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsRuntimeManifestDriftAndToolchainSubstitution()
    {
        using var fixture = new ProofFixture();
        var payload = fixture.CreateValidPayload();
        var after = payload["execution"]!["runtime_manifest_after"]!.AsObject();
        after["entries"]![0]!["sha256"] = new string('c', 64);
        fixture.RefreshManifest(after);
        fixture.WriteProof(payload);

        Assert.Equal("proof_execution_invalid", fixture.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void EvaluateRejectsStaleFutureExpiredAndOverflowingTimes()
    {
        using var stale = new ProofFixture();
        var stalePayload = stale.CreateValidPayload();
        stale.SetTimes(stalePayload, stale.Now.AddHours(-25).AddMinutes(-1), stale.Now.AddHours(-25));
        stale.WriteProof(stalePayload);
        Assert.Equal("proof_stale", stale.CreateService().Evaluate().ReasonCode);

        using var future = new ProofFixture();
        var futurePayload = future.CreateValidPayload();
        future.SetTimes(futurePayload, future.Now.AddMinutes(4), future.Now.AddMinutes(5).AddSeconds(1));
        future.WriteProof(futurePayload);
        Assert.Equal("proof_from_future", future.CreateService().Evaluate().ReasonCode);

        using var expired = new ProofFixture();
        var expiredPayload = expired.CreateValidPayload();
        expired.SetTimes(expiredPayload, expired.Now.AddHours(-24).AddMinutes(-1), expired.Now.AddHours(-24));
        expired.WriteProof(expiredPayload);
        Assert.Equal("proof_expired", expired.CreateService().Evaluate().ReasonCode);

        using var overflow = new ProofFixture();
        var overflowPayload = overflow.CreateValidPayload();
        overflowPayload["started_at"] = "9999-12-31T23:59:58Z";
        overflowPayload["completed_at"] = "9999-12-31T23:59:59Z";
        overflowPayload["generated_at"] = "9999-12-31T23:59:59Z";
        overflowPayload["expires_at"] = "9999-12-31T23:59:59Z";
        overflow.WriteProof(overflowPayload);
        Assert.Equal("proof_timestamp_invalid", overflow.CreateService().Evaluate().ReasonCode);
    }

    [Fact]
    public void SourceLexicalMarkersAreNotIndependentAuthority()
    {
        using var fixture = new ProofFixture();
        fixture.WriteInput("tests/RunServicesSmoke/Program.cs", "// compiled smoke authority is runtime checkpoints\n");
        var payload = fixture.CreateValidPayload();
        fixture.WriteProof(payload);

        Assert.True(fixture.CreateService().Evaluate().IsValid);
    }

    [Fact]
    public void LoadProofReturnsNullForInvalidReceiptAndReasonDoesNotLeakPath()
    {
        using var fixture = new ProofFixture();
        var evaluation = fixture.CreateService().Evaluate();

        Assert.Null(fixture.CreateService().LoadProof());
        Assert.Equal("proof_not_found", evaluation.ReasonCode);
        Assert.DoesNotContain(fixture.Root, evaluation.ReasonCode, StringComparison.Ordinal);
    }

    private static JsonObject ReorderFirstTwo(JsonObject source)
    {
        var properties = source.ToArray();
        var reordered = new JsonObject
        {
            [properties[1].Key] = properties[1].Value?.DeepClone(),
            [properties[0].Key] = properties[0].Value?.DeepClone()
        };
        foreach (var property in properties.Skip(2))
        {
            reordered[property.Key] = property.Value?.DeepClone();
        }

        return reordered;
    }

    private static void MutateTreeRecord(JsonObject record)
    {
        var current = record["tree_sha256"]!.GetValue<string>();
        record["tree_sha256"] = new string(current[0] == '0' ? '1' : '0', 64);
    }

    private static void RefreshClosureDigest(JsonObject closure)
    {
        closure.Remove("closure_sha256");
        closure["closure_sha256"] = CanonicalHash(closure);
    }

    private static string CanonicalHash(JsonNode node)
    {
        using var document = JsonDocument.Parse(node.ToJsonString());
        return Hash(CampaignOsLocalProofService.CanonicalJson(document.RootElement));
    }

    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private sealed class ProofFixture : IDisposable
    {
        private static readonly (string Key, string Path, string Contents)[] Inputs =
        [
            ("source", "tests/RunServicesSmoke/Program.cs", "// smoke program\n"),
            ("journey_spec", ".codex-design/product/GOLDEN_JOURNEY_RELEASE_GATES.yaml", JourneySpec()),
            ("runner", "scripts/ai/run_services_smoke.sh", "#!/bin/sh\nexit 0\n"),
            ("prepare_helper", "scripts/ai/prepare_run_services_smoke.sh", "#!/bin/sh\nexit 0\n"),
            ("environment_helper", "scripts/ai/_env.sh", "#!/bin/sh\nexport TEST=1\n"),
            ("cleanroom_builder", "scripts/ai/build_r1_cleanroom.sh", "#!/bin/sh\nexit 0\n"),
            ("registry_global_usings", "../chummer-hub-registry/Chummer.Run.Registry/GlobalUsings.RegistryContracts.cs", "global using System;\n"),
            ("materializer", "scripts/materialize_campaign_os_local_proof.py", "# materializer\n"),
            ("contract_module", "scripts/campaign_os_local_proof_v3.py", "# contract v3\n")
        ];
        private static readonly Lazy<Toolchain> CurrentToolchain = new(ResolveToolchain);

        private readonly string _canonRoot;
        private readonly MutableClosureProvider _provider;

        public ProofFixture()
        {
            Root = Path.Combine(Path.GetTempPath(), "campaign-os-v3-csharp-tests", Guid.NewGuid().ToString("N"));
            _canonRoot = Path.Combine(Root, "repo");
            ProofPath = Path.Combine(_canonRoot, ".codex-studio", "published", "HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json");
            Now = new DateTimeOffset(2026, 7, 17, 12, 0, 0, TimeSpan.Zero);
            Directory.CreateDirectory(_canonRoot);
            foreach (var (_, path, contents) in Inputs)
            {
                WriteInput(path, contents);
            }

            _provider = new MutableClosureProvider(CreateCandidateClosure(), CreateManagedClosure());
        }

        public string Root { get; }

        public string ProofPath { get; }

        public DateTimeOffset Now { get; }

        public string InputPath(string logicalPath) => Path.GetFullPath(Path.Combine(
            _canonRoot,
            logicalPath.Replace('/', Path.DirectorySeparatorChar)));

        public CampaignOsLocalProofService CreateService()
        {
            var configuration = new ConfigurationBuilder().AddInMemoryCollection(
                new Dictionary<string, string?> { ["CHUMMER_PUBLIC_CANON_ROOT"] = _canonRoot }).Build();
            return new CampaignOsLocalProofService(configuration, new FixedTimeProvider(Now), _provider);
        }

        public JsonObject CreateValidPayload()
        {
            const string runId = "550e8400-e29b-41d4-a716-446655440000";
            var completed = Now.AddMinutes(-5);
            var inputs = new JsonObject();
            foreach (var (key, path, _) in Inputs)
            {
                inputs[key] = CreateIdentity(path, key == "journey_spec");
            }

            var toolchain = CurrentToolchain.Value;
            inputs["dotnet_host"] = new JsonObject
            {
                ["path"] = "/usr/bin/dotnet",
                ["resolved_path"] = toolchain.DotnetPath,
                ["sha256"] = toolchain.DotnetSha256,
                ["size_bytes"] = toolchain.DotnetSize
            };
            inputs["csc"] = new JsonObject
            {
                ["path"] = toolchain.CscPath,
                ["sha256"] = toolchain.CscSha256,
                ["size_bytes"] = toolchain.CscSize
            };
            inputs["assembly"] = new JsonObject
            {
                ["file_name"] = "RunServicesSmoke.dll",
                ["sha256"] = new string('f', 64),
                ["size_bytes"] = 1234L
            };

            var checkpoints = new JsonArray();
            var journeys = new JsonArray();
            foreach (var journeyId in JourneyIds)
            {
                var checkpointId = journeyId + ".run_services_smoke_exit_zero";
                checkpoints.Add(new JsonObject
                {
                    ["checkpoint_id"] = checkpointId,
                    ["run_id"] = runId,
                    ["status"] = "passed"
                });
                journeys.Add(new JsonObject
                {
                    ["id"] = journeyId,
                    ["status"] = "passed",
                    ["checkpoint_ids"] = new JsonArray(checkpointId)
                });
            }

            var candidate = _provider.Candidate.DeepClone().AsObject();
            var staged = CreateStagedClosure(candidate);
            var managed = _provider.Managed.DeepClone().AsObject();
            var manifest = CreateManifest(inputs);
            var checkpointBytes = CheckpointBytes(checkpoints);
            return new JsonObject
            {
                ["contract_name"] = "chummer6-hub.campaign_os_local_proof",
                ["contract_version"] = 3,
                ["status"] = "passed",
                ["proof_kind"] = "materializer_owned_executed_smoke_receipt",
                ["run_id"] = runId,
                ["started_at"] = Format(completed.AddMinutes(-5)),
                ["completed_at"] = Format(completed),
                ["generated_at"] = Format(completed),
                ["expires_at"] = Format(completed.AddHours(24)),
                ["invocation"] = new JsonObject
                {
                    ["id"] = "run_services_smoke",
                    ["owner"] = "campaign_os_local_proof_materializer",
                    ["dependency_mode"] = "restore_free_with_locally_closed_package_inputs",
                    ["prepare_exit_code"] = 0,
                    ["runner_exit_code"] = 0
                },
                ["inputs"] = inputs,
                ["execution"] = new JsonObject
                {
                    ["phase"] = "verified",
                    ["failure_reason"] = null,
                    ["candidate_source_build_inputs_before"] = candidate.DeepClone(),
                    ["candidate_source_build_inputs_after"] = candidate.DeepClone(),
                    ["staged_candidate_inputs_before"] = staged.DeepClone(),
                    ["staged_candidate_inputs_after"] = staged.DeepClone(),
                    ["managed_dotnet_closure_before"] = managed.DeepClone(),
                    ["managed_dotnet_closure_after"] = managed.DeepClone(),
                    ["runtime_manifest_before"] = manifest.DeepClone(),
                    ["runtime_manifest_after"] = manifest.DeepClone(),
                    ["checkpoint_log"] = new JsonObject
                    {
                        ["file_name"] = "campaign-os-checkpoints.jsonl",
                        ["sha256"] = Hash(checkpointBytes),
                        ["size_bytes"] = checkpointBytes.LongLength
                    },
                    ["runtime_checkpoints"] = checkpoints,
                    ["candidate_source_build_inputs_stable"] = true,
                    ["staged_candidate_inputs_stable"] = true,
                    ["managed_dotnet_closure_stable"] = true,
                    ["runtime_closure_stable"] = true,
                    ["closure_stable"] = true
                },
                ["journeys"] = journeys,
                ["summary"] = new JsonObject
                {
                    ["journey_count"] = 6,
                    ["passed_journey_count"] = 6,
                    ["checkpoint_count"] = 6,
                    ["passed_checkpoint_count"] = 6
                }
            };
        }

        public void DriftCurrentCandidateRecord(string collection, int index)
        {
            var record = _provider.Candidate[collection]![index]!.AsObject();
            MutateTreeRecord(record);
            RefreshClosureDigest(_provider.Candidate);
        }

        public void DriftCurrentCandidateRecord(string record)
        {
            MutateTreeRecord(_provider.Candidate[record]!.AsObject());
            RefreshClosureDigest(_provider.Candidate);
        }

        public void DriftCurrentManagedComponent(int index)
        {
            MutateTreeRecord(_provider.Managed["components"]![index]!.AsObject());
            RefreshClosureDigest(_provider.Managed);
        }

        public void RefreshManifest(JsonObject manifest)
        {
            var entries = manifest["entries"]!.AsArray();
            manifest["entry_count"] = entries.Count;
            manifest["manifest_sha256"] = CanonicalHash(entries);
        }

        public void RefreshCheckpointLog(JsonObject payload)
        {
            var checkpoints = payload["execution"]!["runtime_checkpoints"]!.AsArray();
            var bytes = CheckpointBytes(checkpoints);
            payload["execution"]!["checkpoint_log"]!["sha256"] = Hash(bytes);
            payload["execution"]!["checkpoint_log"]!["size_bytes"] = bytes.LongLength;
        }

        public void SetTimes(JsonObject payload, DateTimeOffset started, DateTimeOffset completed)
        {
            payload["started_at"] = Format(started);
            payload["completed_at"] = Format(completed);
            payload["generated_at"] = Format(completed);
            payload["expires_at"] = Format(completed.AddHours(24));
        }

        public void WriteInput(string logicalPath, string contents)
        {
            var fullPath = InputPath(logicalPath);
            Directory.CreateDirectory(Path.GetDirectoryName(fullPath)!);
            File.WriteAllText(fullPath, contents, new UTF8Encoding(false));
        }

        public void WriteValidProof() => WriteProof(CreateValidPayload());

        public void WriteProof(JsonObject payload) => WriteRaw(Serialize(payload));

        public string Serialize(JsonObject payload) => payload.ToJsonString(new JsonSerializerOptions { WriteIndented = false });

        public void WriteRaw(string contents)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(ProofPath)!);
            File.WriteAllText(ProofPath, contents, new UTF8Encoding(false));
        }

        public void Dispose()
        {
            if (Directory.Exists(Root))
            {
                Directory.Delete(Root, recursive: true);
            }
        }

        private JsonObject CreateCandidateClosure()
        {
            string[] projectRoots =
            [
                "../chummer-core-engine/Chummer.Contracts",
                "../chummer-hub-registry/Chummer.Hub.Registry.Contracts",
                "../chummer-hub-registry/Chummer.Run.Registry",
                "../../fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts",
                "../../fleet/repos/chummer-media-factory/src/Chummer.Media.Factory.Runtime",
                "Chummer.Play.Contracts", "Chummer.Campaign.Contracts", "Chummer.Control.Contracts",
                "Chummer.Run.Contracts", "Chummer.World.Contracts", "Chummer.Run.Api",
                "Chummer.Run.Identity", "Chummer.Run.AI"
            ];
            var projectRecords = new JsonArray(projectRoots.Select((root, index) =>
                (JsonNode)Tree(root, index + 1, 100 + index, "abcdef"[index % 6])).ToArray());
            var runtimeRoots = new JsonArray(
                Tree(".codex-design/product", 2, 200, 'c'),
                Tree("../chummer-design/products/chummer", 3, 300, 'd'));
            var packageRootA = Path.Combine(Root, "cache-a");
            var packageRootB = Path.Combine(Root, "cache-b");
            var closure = new JsonObject
            {
                ["kind"] = "candidate_source_build_inputs",
                ["tree_format_version"] = 1,
                ["project_roots"] = projectRecords,
                ["smoke_source_tree"] = Tree("tests/RunServicesSmoke", 1, 50, 'b'),
                ["runtime_data_roots"] = runtimeRoots,
                ["runtime_data_files"] = Tree("runtime_data_files", 1, 10, 'e'),
                ["ancestor_build_controls"] = Tree("ancestor_build_controls", 0, 0, 'f'),
                ["project_assets"] = Tree("project_assets", 13, 1300, '1'),
                ["generated_nuget_imports"] = Tree("generated_nuget_imports", 26, 2600, '2'),
                ["nuget_package_roots"] = new JsonArray(packageRootA, packageRootB),
                ["nuget_packages"] = Tree("project_assets.packageFolders", 4, 4000, '3'),
                ["project_root_count"] = 13,
                ["runtime_data_root_count"] = 2
            };
            RefreshClosureDigest(closure);
            return closure;
        }

        private static JsonObject CreateStagedClosure(JsonObject candidate)
        {
            var project = candidate["project_roots"]!.AsArray()
                .Single(item => item!["root"]!.GetValue<string>() == "Chummer.Run.Api")!.AsObject();
            var runtime = candidate["runtime_data_roots"]!.AsArray();
            var closure = new JsonObject
            {
                ["kind"] = "staged_candidate_inputs",
                ["tree_format_version"] = 1,
                ["roots"] = new JsonArray(
                    Relabel(project, "Chummer.Run.Api"),
                    Relabel(runtime[0]!.AsObject(), ".codex-design/product"),
                    Relabel(runtime[1]!.AsObject(), "products/chummer")),
                ["runtime_data_files"] = candidate["runtime_data_files"]!.DeepClone(),
                ["root_count"] = 3
            };
            RefreshClosureDigest(closure);
            return closure;
        }

        private static JsonObject CreateManagedClosure()
        {
            var toolchain = CurrentToolchain.Value;
            var components = new JsonArray();
            string[] roots =
            [
                "hostfxr", "Microsoft.NETCore.App", "Microsoft.AspNetCore.App",
                "Microsoft.NETCore.App.Ref", "Microsoft.AspNetCore.App.Ref", "sdk"
            ];
            for (var index = 0; index < roots.Length; index++)
            {
                components.Add(new JsonObject
                {
                    ["root"] = roots[index],
                    ["version"] = toolchain.SdkVersion,
                    ["path"] = index == roots.Length - 1
                        ? toolchain.SdkPath
                        : Path.Combine(Path.GetDirectoryName(toolchain.DotnetPath)!, "test-components", roots[index], toolchain.SdkVersion),
                    ["file_count"] = index + 1,
                    ["total_size_bytes"] = 100L + index,
                    ["tree_sha256"] = new string((char)('a' + index), 64)
                });
            }

            var closure = new JsonObject
            {
                ["kind"] = "managed_dotnet_closure",
                ["dotnet_host"] = new JsonObject
                {
                    ["path"] = "/usr/bin/dotnet",
                    ["resolved_path"] = toolchain.DotnetPath,
                    ["sha256"] = toolchain.DotnetSha256,
                    ["size_bytes"] = toolchain.DotnetSize
                },
                ["components"] = components,
                ["component_count"] = 6
            };
            RefreshClosureDigest(closure);
            return closure;
        }

        private JsonObject CreateIdentity(string path, bool version)
        {
            var bytes = File.ReadAllBytes(InputPath(path));
            var identity = new JsonObject
            {
                ["path"] = path,
                ["sha256"] = Hash(bytes),
                ["size_bytes"] = bytes.LongLength
            };
            if (version)
            {
                identity["version"] = 1;
            }

            return identity;
        }

        private static JsonObject CreateManifest(JsonObject inputs)
        {
            string[] paths =
            [
                "Chummer.Campaign.Contracts.dll", "Chummer.Control.Contracts.dll", "Chummer.Engine.Contracts.dll",
                "Chummer.Hub.Registry.Contracts.dll", "Chummer.Media.Contracts.dll", "Chummer.Media.Factory.Runtime.dll",
                "Chummer.Play.Contracts.dll", "Chummer.Run.AI.dll", "Chummer.Run.Api.dll",
                "Chummer.Run.Contracts.dll", "Chummer.Run.Identity.dll", "Chummer.Run.Registry.dll",
                "RunServicesSmoke.dll", "RunServicesSmoke.runtimeconfig.json", "YamlDotNet.dll",
                "toolchain/csc.dll", "toolchain/dotnet"
            ];
            var entries = new JsonArray(paths.Select(path => (JsonNode)new JsonObject
            {
                ["path"] = path,
                ["sha256"] = path switch
                {
                    "RunServicesSmoke.dll" => inputs["assembly"]!["sha256"]!.GetValue<string>(),
                    "toolchain/csc.dll" => inputs["csc"]!["sha256"]!.GetValue<string>(),
                    "toolchain/dotnet" => inputs["dotnet_host"]!["sha256"]!.GetValue<string>(),
                    _ => new string('a', 64)
                },
                ["size_bytes"] = path switch
                {
                    "RunServicesSmoke.dll" => inputs["assembly"]!["size_bytes"]!.GetValue<long>(),
                    "toolchain/csc.dll" => inputs["csc"]!["size_bytes"]!.GetValue<long>(),
                    "toolchain/dotnet" => inputs["dotnet_host"]!["size_bytes"]!.GetValue<long>(),
                    _ => 100L
                }
            }).ToArray());
            return new JsonObject
            {
                ["algorithm"] = "sha256",
                ["entries"] = entries,
                ["entry_count"] = entries.Count,
                ["manifest_sha256"] = CanonicalHash(entries)
            };
        }

        private static JsonObject Tree(string root, long count, long size, char digest) => new()
        {
            ["root"] = root,
            ["file_count"] = count,
            ["total_size_bytes"] = size,
            ["tree_sha256"] = new string(digest, 64)
        };

        private static JsonObject Relabel(JsonObject source, string root) => new()
        {
            ["root"] = root,
            ["file_count"] = source["file_count"]!.DeepClone(),
            ["total_size_bytes"] = source["total_size_bytes"]!.DeepClone(),
            ["tree_sha256"] = source["tree_sha256"]!.DeepClone()
        };

        private static byte[] CheckpointBytes(JsonArray checkpoints) => Encoding.UTF8.GetBytes(
            string.Concat(checkpoints.Select(item => item!.ToJsonString() + "\n")));

        private static Toolchain ResolveToolchain()
        {
            const string dotnetAlias = "/usr/bin/dotnet";
            var dotnetPath = Path.GetFullPath(
                new FileInfo(dotnetAlias).ResolveLinkTarget(returnFinalTarget: true)?.FullName ?? dotnetAlias);
            var dotnetRoot = Path.GetDirectoryName(dotnetPath)!;
            var sdkParent = Path.Combine(dotnetRoot, "sdk");
            var sdkVersion = Directory.EnumerateDirectories(sdkParent)
                .Select(Path.GetFileName)
                .Where(static item => item is not null && item.StartsWith("10.", StringComparison.Ordinal))
                .OrderBy(static item => item, VersionStringComparer.Instance)
                .Last()!;
            var sdkPath = Path.Combine(sdkParent, sdkVersion);
            var cscPath = Path.Combine(sdkPath, "Roslyn", "bincore", "csc.dll");
            var dotnetBytes = File.ReadAllBytes(dotnetPath);
            var cscBytes = File.ReadAllBytes(cscPath);
            return new Toolchain(
                dotnetPath,
                Hash(dotnetBytes),
                dotnetBytes.LongLength,
                sdkVersion,
                sdkPath,
                cscPath,
                Hash(cscBytes),
                cscBytes.LongLength);
        }

        private static string JourneySpec() =>
            "version: 1\njourney_gates:\n" + string.Join("\n", JourneyIds.Select(id => "  - id: " + id)) + "\n";

        public static string Format(DateTimeOffset value) =>
            value.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);

        private sealed record Toolchain(
            string DotnetPath,
            string DotnetSha256,
            long DotnetSize,
            string SdkVersion,
            string SdkPath,
            string CscPath,
            string CscSha256,
            long CscSize);
    }

    private sealed class MutableClosureProvider(JsonObject candidate, JsonObject managed) : ICampaignOsClosureProvider
    {
        public JsonObject Candidate { get; } = candidate;

        public JsonObject Managed { get; } = managed;

        public JsonObject CaptureCandidateSourceBuildInputs(string canonRoot) => Candidate.DeepClone().AsObject();

        public JsonObject CaptureManagedDotnetClosure() => Managed.DeepClone().AsObject();
    }

    private sealed class FixedTimeProvider(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }

    private sealed class VersionStringComparer : IComparer<string?>
    {
        public static VersionStringComparer Instance { get; } = new();

        public int Compare(string? left, string? right)
        {
            if (ReferenceEquals(left, right))
            {
                return 0;
            }

            if (left is null)
            {
                return -1;
            }

            if (right is null)
            {
                return 1;
            }

            var leftParts = System.Text.RegularExpressions.Regex.Matches(left, "[0-9]+")
                .Select(static match => long.Parse(match.Value, CultureInfo.InvariantCulture)).ToArray();
            var rightParts = System.Text.RegularExpressions.Regex.Matches(right, "[0-9]+")
                .Select(static match => long.Parse(match.Value, CultureInfo.InvariantCulture)).ToArray();
            var count = Math.Min(leftParts.Length, rightParts.Length);
            for (var index = 0; index < count; index++)
            {
                var result = leftParts[index].CompareTo(rightParts[index]);
                if (result != 0)
                {
                    return result;
                }
            }

            var length = leftParts.Length.CompareTo(rightParts.Length);
            return length != 0 ? length : string.CompareOrdinal(left, right);
        }
    }
}
