using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Runtime.InteropServices;
using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicProjectionSnapshotServiceTests
{
    [Fact]
    public void HardLinkedCurrentPointerFailsClosed()
    {
        if (!OperatingSystem.IsLinux())
        {
            return;
        }

        using var fixture = new PublicProjectionFixture();
        fixture.PublishValidSnapshot();
        Assert.Equal(
            0,
            CreateHardLinkUnix(
                fixture.CurrentPointerPath,
                fixture.CurrentPointerPath + ".hardlink"));

        PublicProjectionOutputSnapshot projection = new PublicProjectionSnapshotService(
            fixture.CreateConfiguration()).LoadHubLocalReleaseProof();

        Assert.True(projection.IsConfigured);
        Assert.False(projection.IsValid);
    }

    [Fact]
    public void SymlinkedSnapshotOutputFailsClosed()
    {
        if (!OperatingSystem.IsLinux())
        {
            return;
        }

        using var fixture = new PublicProjectionFixture();
        fixture.PublishValidSnapshot();
        string realOutput = fixture.CurrentLocalProofPath + ".real";
        File.Move(fixture.CurrentLocalProofPath, realOutput);
        File.CreateSymbolicLink(fixture.CurrentLocalProofPath, realOutput);

        PublicProjectionOutputSnapshot projection = new PublicProjectionSnapshotService(
            fixture.CreateConfiguration()).LoadHubLocalReleaseProof();

        Assert.True(projection.IsConfigured);
        Assert.False(projection.IsValid);
    }

    [Fact]
    public void DuplicateJsonKeysFailClosed()
    {
        if (!OperatingSystem.IsLinux())
        {
            return;
        }

        using var fixture = new PublicProjectionFixture();
        fixture.PublishValidSnapshot();
        File.WriteAllText(
            fixture.CurrentPointerPath,
            "{\"contractName\":\"chummer.public_projection_current/v1\","
            + "\"contractName\":\"chummer.public_projection_current/v1\"}\n");

        PublicProjectionOutputSnapshot projection = new PublicProjectionSnapshotService(
            fixture.CreateConfiguration()).LoadHubLocalReleaseProof();

        Assert.True(projection.IsConfigured);
        Assert.False(projection.IsValid);
    }

    [Fact]
    public void OversizedCurrentPointerFailsClosed()
    {
        if (!OperatingSystem.IsLinux())
        {
            return;
        }

        using var fixture = new PublicProjectionFixture();
        fixture.PublishValidSnapshot();
        File.WriteAllBytes(fixture.CurrentPointerPath, new byte[256 * 1024 + 1]);

        PublicProjectionOutputSnapshot projection = new PublicProjectionSnapshotService(
            fixture.CreateConfiguration()).LoadHubLocalReleaseProof();

        Assert.True(projection.IsConfigured);
        Assert.False(projection.IsValid);
    }

    [Fact]
    public void AncestorSwapDuringDescriptorResolutionFailsClosed()
    {
        if (!OperatingSystem.IsLinux())
        {
            return;
        }

        string testRoot = Path.Combine(
            Path.GetTempPath(),
            "public-projection-ancestor-swap-tests",
            Guid.NewGuid().ToString("N"));
        string authorityParent = Path.Combine(testRoot, "authority");
        string snapshotRoot = Path.Combine(authorityParent, "snapshots");
        string movedParent = Path.Combine(testRoot, "authority-original");
        try
        {
            using var fixture = new PublicProjectionFixture(snapshotRoot);
            fixture.PublishValidSnapshot();
            var service = new PublicProjectionSnapshotService(
                fixture.CreateConfiguration(),
                () =>
                {
                    Directory.Move(authorityParent, movedParent);
                    Directory.CreateDirectory(snapshotRoot);
                    File.WriteAllText(
                        Path.Combine(snapshotRoot, "CURRENT.json"),
                        "{\"status\":\"attacker\"}\n");
                });

            PublicProjectionOutputSnapshot projection = service.LoadHubLocalReleaseProof();

            Assert.True(projection.IsConfigured);
            Assert.False(projection.IsValid);
        }
        finally
        {
            if (Directory.Exists(testRoot))
            {
                Directory.Delete(testRoot, recursive: true);
            }
        }
    }

    [Fact]
    public void CurrentSnapshotAuthenticatesAndOverridesLegacyDirectProofPath()
    {
        using var fixture = new PublicProjectionFixture();
        fixture.PublishValidSnapshot();
        File.WriteAllText(
            fixture.LegacyProofPath,
            JsonSerializer.Serialize(new
            {
                contract_name = "chummer6-hub.local_release_proof",
                generatedAt = DateTimeOffset.UtcNow,
                status = "legacy-must-not-win",
                proof_routes = new[] { "/legacy" },
                proof_receipts = Array.Empty<object>()
            }));

        IConfiguration configuration = fixture.CreateConfiguration();
        PublicProjectionOutputSnapshot projection =
            new PublicProjectionSnapshotService(configuration).LoadHubLocalReleaseProof();
        LocalReleaseProofSnapshot? local =
            new LocalReleaseProofArtifactService(configuration).LoadSnapshot();

        Assert.True(projection.IsConfigured);
        Assert.True(projection.IsValid, projection.FailureReason);
        Assert.Matches("^public-projection-[0-9a-f]{64}$", projection.SnapshotId);
        Assert.Equal(64, projection.Sha256?.Length);
        Assert.NotNull(local);
        Assert.Equal("passed", local!.Status);
        Assert.Contains("/current", local.ProofRoutes);
        Assert.DoesNotContain("/legacy", local.ProofRoutes);
        Assert.Contains(projection.SnapshotId!, local.Path, StringComparison.Ordinal);
    }

    [Fact]
    public void ReviewRequiredSnapshotCannotAuthorizeReleaseUploadConsumers()
    {
        using var fixture = new PublicProjectionFixture();
        fixture.PublishReviewRequiredSnapshot();

        IConfiguration configuration = fixture.CreateConfiguration();
        PublicProjectionOutputSnapshot projection =
            new PublicProjectionSnapshotService(configuration).LoadHubLocalReleaseProof();

        Assert.True(projection.IsConfigured);
        Assert.False(projection.IsValid);
        Assert.Equal(
            "current public projection snapshot failed authentication",
            projection.FailureReason);
        Assert.Null(new LocalReleaseProofArtifactService(configuration).LoadSnapshot());
    }

    [Fact]
    public void PassingSnapshotWithDisabledReleaseUploadAuthorityFailsClosed()
    {
        using var fixture = new PublicProjectionFixture();
        fixture.PublishInvalidPassPostureSnapshot();

        IConfiguration configuration = fixture.CreateConfiguration();
        PublicProjectionOutputSnapshot projection =
            new PublicProjectionSnapshotService(configuration).LoadHubLocalReleaseProof();

        Assert.True(projection.IsConfigured);
        Assert.False(projection.IsValid);
        Assert.Null(new LocalReleaseProofArtifactService(configuration).LoadSnapshot());
    }

    [Fact]
    public void TamperedOutputFailsClosedForAllLocalProofLookups()
    {
        using var fixture = new PublicProjectionFixture();
        fixture.PublishValidSnapshot();
        File.AppendAllText(fixture.CurrentLocalProofPath, "tamper");

        IConfiguration configuration = fixture.CreateConfiguration();
        PublicProjectionOutputSnapshot projection =
            new PublicProjectionSnapshotService(configuration).LoadHubLocalReleaseProof();
        LocalReleaseProofArtifactService local = new(configuration);

        Assert.True(projection.IsConfigured);
        Assert.False(projection.IsValid);
        Assert.Equal("current public projection snapshot failed authentication", projection.FailureReason);
        Assert.Null(local.LoadSnapshot());
        Assert.Null(local.FindReceipt("/current").ReceiptMatch);
    }

    [Fact]
    public void PointerManifestDigestDriftFailsClosed()
    {
        using var fixture = new PublicProjectionFixture();
        fixture.PublishValidSnapshot();
        using JsonDocument pointer = JsonDocument.Parse(File.ReadAllBytes(fixture.CurrentPointerPath));
        Dictionary<string, object?> drifted = pointer.RootElement.Deserialize<Dictionary<string, object?>>()!;
        drifted["manifestSha256"] = new string('0', 64);
        File.WriteAllText(fixture.CurrentPointerPath, JsonSerializer.Serialize(drifted));

        PublicProjectionOutputSnapshot projection = new PublicProjectionSnapshotService(
            fixture.CreateConfiguration()).LoadHubLocalReleaseProof();

        Assert.True(projection.IsConfigured);
        Assert.False(projection.IsValid);
    }

    [Fact]
    public void RequiredMissingSnapshotNeverFallsBackToLegacyProof()
    {
        using var fixture = new PublicProjectionFixture();
        File.WriteAllText(fixture.LegacyProofPath, "{}");

        IConfiguration configuration = fixture.CreateConfiguration();
        PublicProjectionOutputSnapshot projection =
            new PublicProjectionSnapshotService(configuration).LoadHubLocalReleaseProof();

        Assert.True(projection.IsConfigured);
        Assert.False(projection.IsValid);
        Assert.Null(new LocalReleaseProofArtifactService(configuration).LoadSnapshot());
    }

    internal sealed class PublicProjectionFixture : IDisposable
    {
        private static readonly string[] OutputNames =
        [
            "HUB_LOCAL_RELEASE_PROOF.generated.json",
            "HUB_SERVED_RELEASE_PROOF.generated.json",
            "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
            "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json",
            "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json",
            "RELEASE_CHANNEL.generated.json",
            "FLAGSHIP_PRODUCT_READINESS.generated.json"
        ];

        private readonly string _root;
        private string? _snapshotId;

        public PublicProjectionFixture(string? root = null)
        {
            _root = root ?? Path.Combine(
                Path.GetTempPath(),
                "public-projection-service-tests",
                Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            LegacyProofPath = Path.Combine(_root, "legacy-proof.json");
        }

        public string LegacyProofPath { get; }
        public string SnapshotRoot => _root;
        public string CurrentPointerPath => Path.Combine(_root, "CURRENT.json");
        public string CurrentLocalProofPath => Path.Combine(
            _root,
            _snapshotId!,
            "HUB_LOCAL_RELEASE_PROOF.generated.json");

        public IConfiguration CreateConfiguration()
            => new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    [PublicProjectionSnapshotService.SnapshotRootConfigurationKey] = _root,
                    [PublicProjectionSnapshotService.SnapshotRequiredConfigurationKey] = "true",
                    ["CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE"] = LegacyProofPath,
                    ["CHUMMER_PUBLIC_LOCAL_RELEASE_PROOF_FILE"] = LegacyProofPath
                })
                .Build();

        public void PublishValidSnapshot()
            => PublishSnapshot(
                status: "pass",
                projectionStage: "release_upload_ready",
                codeDeploymentAuthority: true,
                releaseUploadAuthority: true);

        public void PublishReviewRequiredSnapshot()
            => PublishSnapshot(
                status: "review_required",
                projectionStage: "code_deploy_review_required",
                codeDeploymentAuthority: true,
                releaseUploadAuthority: false);

        public void PublishInvalidPassPostureSnapshot()
            => PublishSnapshot(
                status: "pass",
                projectionStage: "release_upload_ready",
                codeDeploymentAuthority: true,
                releaseUploadAuthority: false);

        private void PublishSnapshot(
            string status,
            string projectionStage,
            bool codeDeploymentAuthority,
            bool releaseUploadAuthority)
        {
            byte[] localProof = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contract_name = "chummer6-hub.local_release_proof",
                generatedAt = DateTimeOffset.UtcNow,
                status = "passed",
                proof_routes = new[] { "/current" },
                proof_receipts = Array.Empty<object>()
            });
            var payloads = new Dictionary<string, byte[]>(StringComparer.Ordinal)
            {
                [OutputNames[0]] = localProof,
                [OutputNames[1]] = localProof,
                [OutputNames[2]] = Encoding.UTF8.GetBytes("{\"status\":\"pass\"}\n"),
                [OutputNames[3]] = Encoding.UTF8.GetBytes("{\"status\":\"pass\"}\n"),
                [OutputNames[4]] = Encoding.UTF8.GetBytes("{\"status\":\"pass\"}\n"),
                [OutputNames[5]] = Encoding.UTF8.GetBytes("{\"status\":\"review_required\"}\n"),
                [OutputNames[6]] = Encoding.UTF8.GetBytes("{\"status\":\"fail\"}\n")
            };
            Dictionary<string, string> digests = payloads.ToDictionary(
                static pair => pair.Key,
                static pair => Sha256(pair.Value),
                StringComparer.Ordinal);
            string aggregate = SnapshotDigest(digests);
            _snapshotId = $"public-projection-{aggregate}";
            string snapshotDirectory = Path.Combine(_root, _snapshotId);
            Directory.CreateDirectory(snapshotDirectory);
            foreach ((string name, byte[] payload) in payloads)
            {
                File.WriteAllBytes(Path.Combine(snapshotDirectory, name), payload);
            }

            byte[] manifest = JsonSerializer.SerializeToUtf8Bytes(new Dictionary<string, object?>
            {
                ["contractName"] = "chummer.public_projection_snapshot/v1",
                ["status"] = status,
                ["projectionStage"] = projectionStage,
                ["codeDeploymentAuthority"] = codeDeploymentAuthority,
                ["releaseUploadAuthority"] = releaseUploadAuthority,
                ["snapshotId"] = _snapshotId,
                ["snapshotSha256"] = aggregate,
                ["authorityInputs"] = new Dictionary<string, object?>(),
                ["outputs"] = OutputNames.ToDictionary(
                    static name => name,
                    name => (object)new Dictionary<string, object?>
                    {
                        ["relativePath"] = name,
                        ["sha256"] = digests[name],
                        ["sizeBytes"] = payloads[name].LongLength
                    },
                    StringComparer.Ordinal)
            });
            File.WriteAllBytes(
                Path.Combine(snapshotDirectory, "PUBLIC_PROJECTION_SNAPSHOT.generated.json"),
                manifest);
            File.WriteAllBytes(
                CurrentPointerPath,
                JsonSerializer.SerializeToUtf8Bytes(new Dictionary<string, object?>
                {
                    ["contractName"] = "chummer.public_projection_current/v1",
                    ["status"] = status,
                    ["projectionStage"] = projectionStage,
                    ["codeDeploymentAuthority"] = codeDeploymentAuthority,
                    ["releaseUploadAuthority"] = releaseUploadAuthority,
                    ["snapshotId"] = _snapshotId,
                    ["snapshotSha256"] = aggregate,
                    ["manifestRelativePath"] = $"{_snapshotId}/PUBLIC_PROJECTION_SNAPSHOT.generated.json",
                    ["manifestSha256"] = Sha256(manifest),
                    ["outputs"] = OutputNames.ToDictionary(
                        static name => name,
                        name => (object)$"{_snapshotId}/{name}",
                        StringComparer.Ordinal)
                }));
        }

        private static string SnapshotDigest(IReadOnlyDictionary<string, string> digests)
        {
            using IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            foreach (string name in OutputNames)
            {
                hash.AppendData(Encoding.UTF8.GetBytes(name));
                hash.AppendData([0]);
                hash.AppendData(Encoding.ASCII.GetBytes(digests[name]));
                hash.AppendData([(byte)'\n']);
            }
            return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
        }

        private static string Sha256(byte[] payload)
            => Convert.ToHexString(SHA256.HashData(payload)).ToLowerInvariant();

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    [DllImport("libc", SetLastError = true, EntryPoint = "link")]
    private static extern int CreateHardLinkUnix(string existingPath, string newPath);
}
