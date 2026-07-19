using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseUploadAuthorityHandoffCompatibilityTests
{
    private const string ReleaseCommit = "1111111111111111111111111111111111111111";
    private const string ReadinessCommit = "2222222222222222222222222222222222222222";

    private static readonly string[] ExpectedAuthorityVariableNames =
    [
        "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_COMMIT",
        "CHUMMER_HUB_RELEASE_CHANNEL_PATH",
        "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256",
        "CHUMMER_HUB_RELEASE_CHANNEL_AUTHORITY",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_SHA256",
        "CHUMMER_FLAGSHIP_PRODUCT_READINESS_AUTHORITY",
        "CHUMMER_FLEET_QUEUE_STAGING_PATH",
        "CHUMMER_FLEET_QUEUE_STAGING_EXPECTED_SHA256",
        "CHUMMER_FLEET_QUEUE_STAGING_AUTHORITY",
        "CHUMMER_DESIGN_QUEUE_STAGING_PATH",
        "CHUMMER_DESIGN_QUEUE_STAGING_EXPECTED_SHA256",
        "CHUMMER_DESIGN_QUEUE_STAGING_AUTHORITY",
        "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH",
        "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256",
        "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_AUTHORITY"
    ];

    [Fact]
    public async Task RealMaterializerOutputRoundTripsThroughFiveInputSeventeenVariableHandoff()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        string tempRoot = Path.Combine(
            Path.GetTempPath(),
            "chummer-real-authority-handoff-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        try
        {
            string generatedAt = DateTimeOffset.UtcNow.ToString(
                "yyyy-MM-dd'T'HH:mm:ss'Z'",
                System.Globalization.CultureInfo.InvariantCulture);
            Dictionary<string, string> sourceEnvironment = BuildSourceAuthorityEnvironment(
                tempRoot,
                generatedAt);
            string firstOutput = Path.Combine(
                tempRoot,
                "first",
                "HUB_LOCAL_RELEASE_PROOF.generated.json");

            MaterializerResult first = await RunMaterializerAsync(
                tempRoot,
                firstOutput,
                sourceEnvironment,
                "first-public-edge-mutation.lock");
            Assert.True(
                first.ExitCode == 0,
                $"real materializer failed ({first.ExitCode})\nstdout:\n{first.Stdout}\nstderr:\n{first.Stderr}");

            byte[] proofBytes = await File.ReadAllBytesAsync(firstOutput);
            using (JsonDocument proofDocument = JsonDocument.Parse(proofBytes))
            {
                Assert.True(proofDocument.RootElement.TryGetProperty("proof_routes", out _));
                Assert.False(proofDocument.RootElement.TryGetProperty("proofRoutes", out _));
            }

            ReleaseUploadAuthorityHandoff handoff =
                ReleaseUploadAuthorityHandoffBuilder.Build(Snapshot(proofBytes));
            Assert.Equal(5, handoff.Inputs.Count);

            string hydratedRoot = Path.Combine(tempRoot, "hydrated-authorities");
            Directory.CreateDirectory(hydratedRoot);
            var derivedEnvironment = new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT"] =
                    handoff.ReleaseChannelExpectedCommit,
                ["CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_COMMIT"] =
                    handoff.FlagshipReadinessExpectedCommit
            };
            foreach (ReleaseUploadAuthorityInput input in handoff.Inputs)
            {
                string path = Path.Combine(hydratedRoot, input.FileName);
                await File.WriteAllBytesAsync(path, input.Payload);
                derivedEnvironment[input.PathEnvironmentVariable] = path;
                derivedEnvironment[input.DigestEnvironmentVariable] = input.Sha256;
                derivedEnvironment[input.AuthorityEnvironmentVariable] = input.Authority;
            }

            Assert.Equal(
                ExpectedAuthorityVariableNames.OrderBy(static value => value, StringComparer.Ordinal),
                derivedEnvironment.Keys.OrderBy(static value => value, StringComparer.Ordinal));

            string secondOutput = Path.Combine(
                tempRoot,
                "second",
                "HUB_LOCAL_RELEASE_PROOF.generated.json");
            MaterializerResult second = await RunMaterializerAsync(
                tempRoot,
                secondOutput,
                derivedEnvironment,
                "second-public-edge-mutation.lock");
            Assert.True(
                second.ExitCode == 0,
                $"real materializer rejected the 17-variable handoff ({second.ExitCode})\n"
                + $"stdout:\n{second.Stdout}\nstderr:\n{second.Stderr}");

            using JsonDocument roundTrip = JsonDocument.Parse(
                await File.ReadAllBytesAsync(secondOutput));
            JsonElement authorityInputs = roundTrip.RootElement.GetProperty("authority_inputs");
            Assert.Equal(5, authorityInputs.EnumerateObject().Count());
            foreach (ReleaseUploadAuthorityInput input in handoff.Inputs)
            {
                JsonElement metadata = authorityInputs.GetProperty(input.Key);
                Assert.Equal(input.Sha256, metadata.GetProperty("sha256").GetString());
                Assert.Equal(input.Authority, metadata.GetProperty("authority").GetString());
            }
            Assert.Equal(
                handoff.ReleaseChannelExpectedCommit,
                authorityInputs.GetProperty("release_channel").GetProperty("commit").GetString());
            Assert.Equal(
                handoff.FlagshipReadinessExpectedCommit,
                authorityInputs.GetProperty("flagship_readiness").GetProperty("commit").GetString());

            JsonObject withMatchingCompatibilityAlias = JsonNode.Parse(proofBytes)!.AsObject();
            withMatchingCompatibilityAlias["proofRoutes"] =
                withMatchingCompatibilityAlias["proof_routes"]!.DeepClone();
            _ = ReleaseUploadAuthorityHandoffBuilder.Build(
                Snapshot(JsonSerializer.SerializeToUtf8Bytes(withMatchingCompatibilityAlias)));

            withMatchingCompatibilityAlias["proofRoutes"] = new JsonArray(
                "/downloads/install/disagreeing-installer");
            Assert.Throws<InvalidDataException>(() =>
                ReleaseUploadAuthorityHandoffBuilder.Build(
                    Snapshot(JsonSerializer.SerializeToUtf8Bytes(withMatchingCompatibilityAlias))));

            JsonObject compatibilityAliasOnly = JsonNode.Parse(proofBytes)!.AsObject();
            compatibilityAliasOnly["proofRoutes"] =
                compatibilityAliasOnly["proof_routes"]!.DeepClone();
            compatibilityAliasOnly.Remove("proof_routes");
            Assert.Throws<InvalidDataException>(() =>
                ReleaseUploadAuthorityHandoffBuilder.Build(
                    Snapshot(JsonSerializer.SerializeToUtf8Bytes(compatibilityAliasOnly))));
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    [Fact]
    public async Task BuilderRejectsPaddedCanonicalProofRouteValue()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        byte[] proofBytes = await MaterializeCanonicalProofAsync();
        JsonObject paddedCanonical = JsonNode.Parse(proofBytes)!.AsObject();
        JsonArray canonicalRoutes = paddedCanonical["proof_routes"]!.AsArray();
        canonicalRoutes[0] = " " + canonicalRoutes[0]!.GetValue<string>();

        Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadAuthorityHandoffBuilder.Build(
                Snapshot(JsonSerializer.SerializeToUtf8Bytes(paddedCanonical))));
    }

    [Fact]
    public async Task BuilderRejectsWhitespaceDifferentProofRouteAliasArray()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        byte[] proofBytes = await MaterializeCanonicalProofAsync();
        JsonObject whitespaceAlias = JsonNode.Parse(proofBytes)!.AsObject();
        JsonArray compatibilityRoutes =
            whitespaceAlias["proof_routes"]!.DeepClone().AsArray();
        compatibilityRoutes[0] = compatibilityRoutes[0]!.GetValue<string>() + " ";
        whitespaceAlias["proofRoutes"] = compatibilityRoutes;

        Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadAuthorityHandoffBuilder.Build(
                Snapshot(JsonSerializer.SerializeToUtf8Bytes(whitespaceAlias))));
    }

    private static Dictionary<string, string> BuildSourceAuthorityEnvironment(
        string root,
        string generatedAt)
    {
        string releasePath = Path.Combine(root, "RELEASE_CHANNEL.generated.json");
        string readinessPath = Path.Combine(root, "FLAGSHIP_PRODUCT_READINESS.generated.json");
        string releaseSha256 = WriteJson(
            releasePath,
            new
            {
                contractName = "Chummer.Hub.Registry.Contracts",
                contract_name = "Chummer.Hub.Registry.Contracts",
                generatedAt,
                generated_at = generatedAt,
                publishedAt = generatedAt,
                channelId = "preview",
                channel = "preview",
                releaseVersion = "run-test",
                version = "run-test",
                rolloutState = "promoted_preview",
                supportabilityState = "review_required",
                registryCommit = ReleaseCommit,
                registry_commit = ReleaseCommit,
                artifacts = new[]
                {
                    new { artifactId = "avalonia-linux-x64-installer", kind = "installer" },
                    new { artifactId = "avalonia-osx-arm64-installer", kind = "installer" },
                    new { artifactId = "avalonia-win-x64-installer", kind = "installer" }
                }
            });
        string readinessSha256 = WriteJson(
            readinessPath,
            new
            {
                contract_name = "fleet.flagship_product_readiness",
                generated_at = generatedAt,
                status = "fail",
                scoped_status = "fail",
                missing_keys = new[] { "desktop_client" },
                scoped_missing_keys = new[] { "desktop_client" },
                completion_audit = new { status = "fail", reason = "review required" },
                sourceCommit = ReadinessCommit,
                source_commit = ReadinessCommit,
                flagship_readiness_audit = new
                {
                    reason = "review required",
                    missing_coverage_keys = new[] { "desktop_client" },
                    scoped_missing_coverage_keys = new[] { "desktop_client" }
                }
            });

        string fleetQueue = Path.Combine(root, "fleet-authority.yaml");
        string designQueue = Path.Combine(root, "design-authority.yaml");
        string designRegistry = Path.Combine(root, "design-registry-authority.yaml");
        File.WriteAllText(fleetQueue, "items: []\n", Encoding.UTF8);
        File.WriteAllText(designQueue, "items: []\n", Encoding.UTF8);
        File.WriteAllText(designRegistry, "entries: []\n", Encoding.UTF8);

        return new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT"] = ReleaseCommit,
            ["CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_COMMIT"] = ReadinessCommit,
            ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = releasePath,
            ["CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256"] = releaseSha256,
            ["CHUMMER_HUB_RELEASE_CHANNEL_AUTHORITY"] = "registry://release/run-test",
            ["CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH"] = readinessPath,
            ["CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_SHA256"] = readinessSha256,
            ["CHUMMER_FLAGSHIP_PRODUCT_READINESS_AUTHORITY"] = "fleet://readiness/run-test",
            ["CHUMMER_FLEET_QUEUE_STAGING_PATH"] = fleetQueue,
            ["CHUMMER_FLEET_QUEUE_STAGING_EXPECTED_SHA256"] = Sha256(fleetQueue),
            ["CHUMMER_FLEET_QUEUE_STAGING_AUTHORITY"] = "fleet://queue/run-test",
            ["CHUMMER_DESIGN_QUEUE_STAGING_PATH"] = designQueue,
            ["CHUMMER_DESIGN_QUEUE_STAGING_EXPECTED_SHA256"] = Sha256(designQueue),
            ["CHUMMER_DESIGN_QUEUE_STAGING_AUTHORITY"] = "repo://design/run-test/queue",
            ["CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH"] = designRegistry,
            ["CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256"] = Sha256(designRegistry),
            ["CHUMMER_DESIGN_SUCCESSOR_REGISTRY_AUTHORITY"] =
                "repo://design/run-test/registry"
        };
    }

    private static async Task<byte[]> MaterializeCanonicalProofAsync()
    {
        string tempRoot = Path.Combine(
            Path.GetTempPath(),
            "chummer-canonical-proof-routes-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        try
        {
            string generatedAt = DateTimeOffset.UtcNow.ToString(
                "yyyy-MM-dd'T'HH:mm:ss'Z'",
                System.Globalization.CultureInfo.InvariantCulture);
            Dictionary<string, string> sourceEnvironment = BuildSourceAuthorityEnvironment(
                tempRoot,
                generatedAt);
            string output = Path.Combine(
                tempRoot,
                "output",
                "HUB_LOCAL_RELEASE_PROOF.generated.json");
            MaterializerResult result = await RunMaterializerAsync(
                tempRoot,
                output,
                sourceEnvironment,
                "canonical-proof-routes.lock");
            Assert.True(
                result.ExitCode == 0,
                $"real materializer failed ({result.ExitCode})\n"
                + $"stdout:\n{result.Stdout}\nstderr:\n{result.Stderr}");
            return await File.ReadAllBytesAsync(output);
        }
        finally
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    private static async Task<MaterializerResult> RunMaterializerAsync(
        string workingDirectory,
        string output,
        IReadOnlyDictionary<string, string> authorityEnvironment,
        string lockFileName)
    {
        var startInfo = new ProcessStartInfo("python3")
        {
            WorkingDirectory = workingDirectory,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false
        };
        startInfo.ArgumentList.Add(RepoPaths.FromRoot(
            "scripts",
            "materialize_hub_local_release_proof.py"));
        startInfo.ArgumentList.Add(output);
        startInfo.ArgumentList.Add("https://chummer.run");
        startInfo.ArgumentList.Add("docker-compose.yml");
        startInfo.ArgumentList.Add("120");
        startInfo.ArgumentList.Add("true");
        foreach (string name in ExpectedAuthorityVariableNames)
        {
            startInfo.Environment.Remove(name);
        }
        foreach ((string name, string value) in authorityEnvironment)
        {
            startInfo.Environment[name] = value;
        }
        startInfo.Environment["CHUMMER_REQUIRE_CURRENT_RELEASE_INPUTS"] = "1";
        startInfo.Environment["CHUMMER_VERIFY_RELEASE_PROOF_MAX_AGE_SECONDS"] = "86400";
        startInfo.Environment["CHUMMER_VERIFY_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS"] = "300";
        startInfo.Environment["CHUMMER_HUB_LOCAL_PROOF_MUTATION_LOCK_PATH"] =
            Path.Combine(workingDirectory, ".lock", lockFileName);

        using Process process = Process.Start(startInfo)
            ?? throw new InvalidOperationException("real Hub materializer did not start");
        Task<string> stdout = process.StandardOutput.ReadToEndAsync();
        Task<string> stderr = process.StandardError.ReadToEndAsync();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(60));
        await process.WaitForExitAsync(timeout.Token);
        return new MaterializerResult(
            process.ExitCode,
            await stdout,
            await stderr);
    }

    private static PublicProjectionOutputSnapshot Snapshot(byte[] proofBytes)
    {
        string snapshotSha256 = new string('a', 64);
        return new PublicProjectionOutputSnapshot(
            IsConfigured: true,
            IsValid: true,
            FailureReason: null,
            SnapshotId: "public-projection-" + snapshotSha256,
            SnapshotSha256: snapshotSha256,
            Path: null,
            Sha256: Convert.ToHexStringLower(SHA256.HashData(proofBytes)),
            Payload: proofBytes);
    }

    private static string WriteJson(string path, object value)
    {
        byte[] payload = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(value) + "\n");
        File.WriteAllBytes(path, payload);
        return Convert.ToHexStringLower(SHA256.HashData(payload));
    }

    private static string Sha256(string path)
        => Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path)));

    private sealed record MaterializerResult(int ExitCode, string Stdout, string Stderr);
}
