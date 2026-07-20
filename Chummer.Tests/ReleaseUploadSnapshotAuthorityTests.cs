using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseUploadSnapshotAuthorityTests
{
    [Fact]
    public void RawFleetCredentialCannotBypassMissingOrReviewOnlySnapshotPolicy()
    {
        using var fixture = new SnapshotFixture();
        Assert.Null(fixture.Evaluate());

        fixture.Publish("review_required");

        Assert.Null(fixture.Evaluate());
        ReleaseUploadSnapshotAuthority review = fixture.Authority.Load();
        Assert.True(review.IsValid, review.FailureReason);
        Assert.False(review.ReleaseUploadAuthority);
        Assert.False(review.CandidateImportAuthority);
    }

    [Fact]
    public void FullPassSnapshotAuthorizesFleetCredentialAndPrivilegedReconciliation()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish("pass");

        ReleaseUploadAuthorizationContext authorization = Assert.IsType<ReleaseUploadAuthorizationContext>(
            fixture.Evaluate());

        Assert.False(authorization.SingleUseAuthorization);
        Assert.True(authorization.AllowsPrivilegedReconciliation);
        Assert.Null(authorization.CandidateImportAuthority);
        Assert.Matches("^[0-9a-f]{64}$", authorization.AuthorizationBinding);
    }

    [Fact]
    public void CandidateSnapshotRequiresExactHeadersAndForcesSingleUseFleetAuthorization()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish("candidate_import_ready");
        ReleaseUploadCandidateAuthority candidate = Assert.IsType<ReleaseUploadCandidateAuthority>(
            fixture.Authority.Load().Candidate);

        Assert.Null(fixture.Evaluate());
        ReleaseUploadAuthorizationContext exact = Assert.IsType<ReleaseUploadAuthorizationContext>(
            fixture.Evaluate(candidate.Candidate));

        Assert.True(exact.SingleUseAuthorization);
        Assert.False(exact.AllowsPrivilegedReconciliation);
        Assert.Equal(candidate.SessionBinding, exact.CandidateImportAuthority?.SessionBinding);
        Assert.Equal(candidate.ExpiresAtUtc, exact.AuthorizationExpiresAtUtc);

        ReleaseUploadCandidateIdentity mismatch = candidate.Candidate with
        {
            InventorySha256 = new string('f', 64)
        };
        Assert.Null(fixture.Evaluate(mismatch));
    }

    [Fact]
    public void CandidateBundleValidatorRejectsAnyExtraOrChangedStagedByte()
    {
        using var fixture = new SnapshotFixture();
        fixture.Publish("candidate_import_ready");
        ReleaseUploadCandidateAuthority candidate = Assert.IsType<ReleaseUploadCandidateAuthority>(
            fixture.Authority.Load().Candidate);
        string bundle = fixture.CreateExactBundle(candidate);

        ReleaseUploadCandidateBundleValidator.Validate(bundle, candidate);
        File.WriteAllText(Path.Combine(bundle, "unexpected.bin"), "extra");

        InvalidDataException rejected = Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadCandidateBundleValidator.Validate(bundle, candidate));
        Assert.Contains("exact candidate authority inventory", rejected.Message, StringComparison.Ordinal);
    }

    private sealed class SnapshotFixture : IDisposable
    {
        private static readonly string[] BaseOutputNames =
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
        private readonly IDataProtectionProvider _protection;

        public SnapshotFixture()
        {
            _root = Path.Combine(
                Path.GetTempPath(),
                "release-upload-snapshot-authority-tests",
                Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    [PublicProjectionSnapshotService.SnapshotRootConfigurationKey] = _root,
                    [PublicProjectionSnapshotService.SnapshotRequiredConfigurationKey] = "true",
                    ["FLEET_INTERNAL_API_TOKEN"] = "fleet-test-token"
                })
                .Build();
            _protection = DataProtectionProvider.Create(
                new DirectoryInfo(Path.Combine(_root, "keys")));
            Tickets = new ReleaseUploadTicketService(_protection, Configuration);
            Authority = new ReleaseUploadSnapshotAuthorityService(Configuration);
            Evaluator = new ReleaseUploadAuthorizationEvaluator(
                Configuration,
                Tickets,
                Authority);
        }

        public IConfiguration Configuration { get; }
        public ReleaseUploadTicketService Tickets { get; }
        public ReleaseUploadSnapshotAuthorityService Authority { get; }
        public ReleaseUploadAuthorizationEvaluator Evaluator { get; }

        public ReleaseUploadAuthorizationContext? Evaluate(
            ReleaseUploadCandidateIdentity? candidate = null)
        {
            var context = new DefaultHttpContext();
            context.Request.Method = HttpMethods.Post;
            context.Request.Path = "/api/internal/releases/upload-sessions";
            context.Request.Headers.Authorization = "Bearer fleet-test-token";
            if (candidate is not null)
            {
                context.Request.Headers[
                    ReleaseUploadAuthorizationEvaluator.CandidateManifestSha256Header] =
                    candidate.CanonicalManifestSha256;
                context.Request.Headers[
                    ReleaseUploadAuthorizationEvaluator.CandidateInventorySha256Header] =
                    candidate.InventorySha256;
                context.Request.Headers[
                    ReleaseUploadAuthorizationEvaluator.CandidateBundleIdentitySha256Header] =
                    candidate.BundleIdentitySha256;
            }
            return Evaluator.Evaluate(context.Request);
        }

        public void Publish(string status)
        {
            byte[] local = "{\"status\":\"projection\"}\n"u8.ToArray();
            var payloads = BaseOutputNames.ToDictionary(
                static name => name,
                _ => "{\"status\":\"test\"}\n"u8.ToArray(),
                StringComparer.Ordinal);
            payloads[BaseOutputNames[0]] = local;
            payloads[BaseOutputNames[1]] = local;
            if (status == "candidate_import_ready")
            {
                payloads[ReleaseUploadSnapshotAuthorityService.CandidateAuthorityFileName] =
                    BuildCandidateAuthority();
            }
            string[] outputNames = payloads.Keys.ToArray();
            var digests = payloads.ToDictionary(
                static pair => pair.Key,
                static pair => Sha256(pair.Value),
                StringComparer.Ordinal);
            string aggregate = SnapshotDigest(outputNames, digests);
            string snapshotId = $"public-projection-{aggregate}";
            string directory = Path.Combine(_root, snapshotId);
            Directory.CreateDirectory(directory);
            foreach ((string name, byte[] payload) in payloads)
            {
                File.WriteAllBytes(Path.Combine(directory, name), payload);
            }
            (string stage, bool code, bool release, bool candidate) = status switch
            {
                "pass" => ("release_upload_ready", true, true, false),
                "review_required" => ("code_deploy_review_required", true, false, false),
                "candidate_import_ready" => ("candidate_import_ready", false, false, true),
                _ => throw new ArgumentOutOfRangeException(nameof(status))
            };
            object[] findings = status switch
            {
                "pass" => [],
                "review_required" =>
                [
                    new
                    {
                        gate = "live public Windows installer",
                        status = "postdeploy_required",
                        reason = "live Windows installer proof must pass after code deployment"
                    }
                ],
                _ =>
                [
                    new
                    {
                        gate = "live release convergence after candidate import",
                        status = "postdeploy_required",
                        reason = "candidate bytes require live verification before release upload authority can be restored"
                    }
                ]
            };
            var common = new Dictionary<string, object?>
            {
                ["status"] = status,
                ["projectionStage"] = stage,
                ["codeDeploymentAuthority"] = code,
                ["releaseUploadAuthority"] = release,
                ["candidateImportAuthority"] = candidate,
                ["releaseGateFindings"] = findings,
                ["snapshotId"] = snapshotId,
                ["snapshotSha256"] = aggregate
            };
            var manifest = new Dictionary<string, object?>(common)
            {
                ["contractName"] = "chummer.public_projection_snapshot/v1",
                ["authorityInputs"] = new Dictionary<string, object?>(),
                ["outputs"] = outputNames.ToDictionary(
                    static name => name,
                    name => (object)new Dictionary<string, object?>
                    {
                        ["relativePath"] = name,
                        ["sha256"] = digests[name],
                        ["sizeBytes"] = payloads[name].LongLength
                    },
                    StringComparer.Ordinal)
            };
            byte[] manifestBytes = JsonSerializer.SerializeToUtf8Bytes(manifest);
            File.WriteAllBytes(
                Path.Combine(directory, "PUBLIC_PROJECTION_SNAPSHOT.generated.json"),
                manifestBytes);
            var pointer = new Dictionary<string, object?>(common)
            {
                ["contractName"] = "chummer.public_projection_current/v1",
                ["manifestRelativePath"] =
                    $"{snapshotId}/PUBLIC_PROJECTION_SNAPSHOT.generated.json",
                ["manifestSha256"] = Sha256(manifestBytes),
                ["outputs"] = outputNames.ToDictionary(
                    static name => name,
                    name => (object)$"{snapshotId}/{name}",
                    StringComparer.Ordinal)
            };
            File.WriteAllBytes(
                Path.Combine(_root, "CURRENT.json"),
                JsonSerializer.SerializeToUtf8Bytes(pointer));
        }

        public string CreateExactBundle(ReleaseUploadCandidateAuthority authority)
        {
            string root = Path.Combine(_root, "exact-bundle");
            Directory.CreateDirectory(root);
            foreach (ReleaseUploadCandidateInventoryRow row in authority.Inventory)
            {
                string path = Path.Combine(root, row.Path.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                File.WriteAllBytes(path, authority.CanonicalManifestBytes);
            }
            return root;
        }

        private static byte[] BuildCandidateAuthority()
        {
            byte[] canonical = "{\"version\":\"run-candidate\"}\n"u8.ToArray();
            string canonicalSha = Sha256(canonical);
            var rows = new[]
            {
                new ReleaseUploadCandidateInventoryRow(
                    "RELEASE_CHANNEL.generated.json",
                    canonical.LongLength,
                    canonicalSha)
            };
            string inventorySha =
                ReleaseUploadSnapshotAuthorityService.ComputeInventoryDigest(rows);
            var candidate = new ReleaseUploadCandidateIdentity(
                "run-candidate",
                canonicalSha,
                inventorySha,
                1,
                canonical.LongLength,
                string.Empty);
            candidate = candidate with
            {
                BundleIdentitySha256 =
                    ReleaseUploadSnapshotAuthorityService.ComputeBundleIdentity(candidate)
            };
            byte[] inventory = JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer.release-upload.candidate-inventory/v1",
                contractVersion = 1,
                files = rows.Select(row => new
                {
                    path = row.Path,
                    sha256 = row.Sha256,
                    sizeBytes = row.SizeBytes
                })
            });
            string[] evidencePaths =
            [
                "WINDOWS_NATIVE_CAPTURE.generated.json",
                "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json",
                "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json",
                "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json",
                "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json",
                "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json",
                "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json",
                "startup-smoke/startup-smoke-blazor-desktop-win-x64.receipt.json"
            ];
            return JsonSerializer.SerializeToUtf8Bytes(new
            {
                contractName = "chummer.release-upload.candidate-import-authority/v1",
                contractVersion = 1,
                status = "candidate_import_ready",
                generatedAtUtc = DateTimeOffset.UtcNow,
                expiresAtUtc = DateTimeOffset.UtcNow.AddHours(2),
                candidate = new
                {
                    version = candidate.Version,
                    canonicalManifestSha256 = candidate.CanonicalManifestSha256,
                    inventorySha256 = candidate.InventorySha256,
                    fileCount = candidate.FileCount,
                    totalBytes = candidate.TotalBytes,
                    bundleIdentitySha256 = candidate.BundleIdentitySha256
                },
                custody = new
                {
                    canonicalManifest = Embedded("RELEASE_CHANNEL.generated.json", canonical),
                    inventory = Embedded("CANDIDATE_UPLOAD_INVENTORY.generated.json", inventory),
                    nativeWindowsFinalizedEvidence = new
                    {
                        status = "passed",
                        captureGeneratedAtUtc = DateTimeOffset.UtcNow,
                        finalizationGeneratedAtUtc = DateTimeOffset.UtcNow,
                        reviewer = "accountable-reviewer",
                        captureSource = new
                        {
                            actor = "github-actions[bot]",
                            workflow = ".github/workflows/windows-native-evidence-capture.yml"
                        },
                        finalizationSource = new
                        {
                            actor = "accountable-reviewer",
                            workflow = ".github/workflows/windows-native-evidence-finalize.yml"
                        },
                        candidateContentInventorySha256 = new string('a', 64),
                        candidateContentInventory = new { },
                        files = evidencePaths.Select(path => Embedded(path, "{}"u8.ToArray()))
                    }
                }
            });
        }

        private static object Embedded(string path, byte[] payload)
            => new
            {
                path,
                sha256 = Sha256(payload),
                sizeBytes = payload.LongLength,
                @base64 = Convert.ToBase64String(payload)
            };

        private static string SnapshotDigest(
            IEnumerable<string> names,
            IReadOnlyDictionary<string, string> digests)
        {
            using IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            foreach (string name in names)
            {
                hash.AppendData(Encoding.UTF8.GetBytes(name));
                hash.AppendData([0]);
                hash.AppendData(Encoding.ASCII.GetBytes(digests[name]));
                hash.AppendData([(byte)'\n']);
            }
            return Convert.ToHexStringLower(hash.GetHashAndReset());
        }

        private static string Sha256(byte[] payload)
            => Convert.ToHexStringLower(SHA256.HashData(payload));

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
