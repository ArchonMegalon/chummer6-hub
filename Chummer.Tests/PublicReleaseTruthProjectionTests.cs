using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Http;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicReleaseTruthProjectionTests
{
    private const string RegistryCommit = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

    [Fact]
    public void ProjectionPublishesTheCompleteDeterministicConvergenceContract()
    {
        PublicReleaseManifestDto manifest = BuildManifest(
            BuildArtifact("windows", "windows", "avalonia", 'd', "open_public"),
            BuildArtifact("linux-legacy", "linux", "legacy", 'e', "account_required"),
            BuildArtifact("linux-primary", "linux", "avalonia", 'f', "open_public"));
        AuthorityEnvelope authority = BuildAuthorityEnvelope(
            manifest,
            "stable_ready",
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["linux"] = "avalonia",
                ["windows"] = "avalonia"
            });

        PublicReleaseTruthProjectionDto projection = ProjectAuthority(manifest, authority);

        Assert.Equal(PublicReleaseTruthProjectionDto.Schema, projection.ContractName);
        Assert.Equal("6.2.0", projection.ReleaseVersion);
        Assert.Equal("public_stable", projection.Channel);
        Assert.Equal("published", projection.ReleaseStatus);
        Assert.Equal("public_stable", projection.RolloutState);
        Assert.Equal("gold_supported", projection.SupportabilityState);
        Assert.Equal(["linux", "windows"], projection.AvailablePlatforms);
        Assert.Equal("avalonia", projection.PrimaryHeadByPlatform["linux"]);
        Assert.Equal("avalonia", projection.PrimaryHeadByPlatform["windows"]);
        Assert.Equal(3, projection.ArtifactCount);
        Assert.Equal("mixed", projection.DownloadAccessPosture);
        Assert.Equal("Known caution.", projection.KnownIssueSummary);
        Assert.Equal(Digest(authority.ManifestBytes), projection.ManifestSha256);
        Assert.Equal(RegistryCommit, projection.RegistryCommit);
        Assert.Equal("stable_ready", projection.ReleaseDecisionStatus);
        Assert.Equal(Digest(authority.DecisionBytes), projection.ReleaseDecisionSha256);
        Assert.True(projection.AuthorityBound);
        Assert.True(projection.AvailabilityClaimsAllowed);
        Assert.True(projection.StableClaimsAllowed);

        using JsonDocument serialized = JsonDocument.Parse(JsonSerializer.Serialize(projection));
        foreach (string requiredField in new[]
                 {
                     "releaseVersion", "channel", "releaseStatus", "rolloutState",
                     "supportabilityState", "availablePlatforms", "primaryHeadByPlatform",
                     "artifactCount", "downloadAccessPosture", "knownIssueSummary",
                     "manifestSha256", "registryCommit", "releaseDecisionStatus",
                     "releaseDecisionSha256"
                 })
        {
            Assert.True(serialized.RootElement.TryGetProperty(requiredField, out _), requiredField);
        }
    }

    [Fact]
    public void ManifestCannotSelfDeclareDecisionAuthority()
    {
        ReadOnlyMemory<byte> manifestBytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
        {
            registryCommit = RegistryCommit,
            releaseDecisionStatus = "stable_ready",
            releaseDecisionSha256 = new string('c', 64)
        }));

        PublicReleaseTruthProjectionDto projection =
            PublicReleaseTruthProjectionService.BuildProjection(
                BuildManifest(BuildPublicArtifact()),
                Digest(manifestBytes),
                manifestBytes);

        Assert.Equal(Digest(manifestBytes), projection.ManifestSha256);
        Assert.Equal(PublicReleaseTruthProjectionDto.Missing, projection.RegistryCommit);
        Assert.Equal(PublicReleaseTruthProjectionDto.Missing, projection.ReleaseDecisionStatus);
        Assert.Equal(PublicReleaseTruthProjectionDto.Missing, projection.ReleaseDecisionSha256);
        Assert.False(projection.AuthorityBound);
        Assert.False(projection.AvailabilityClaimsAllowed);
        Assert.True(projection.ReviewBannerRequired);
    }

    [Fact]
    public void UnknownDecisionAuthorityIsRejected()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(manifest, "approved");

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, authority));
    }

    [Fact]
    public void ReviewRequiredKeepsArtifactProjectionButWithholdsOptimisticClaims()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        PublicReleaseTruthProjectionDto projection = ProjectAuthority(
            manifest,
            BuildAuthorityEnvelope(manifest, "review_required"));

        Assert.Equal(1, projection.ArtifactCount);
        Assert.Equal(["windows"], projection.AvailablePlatforms);
        Assert.Equal("open_public", projection.DownloadAccessPosture);
        Assert.True(projection.AuthorityBound);
        Assert.False(projection.AvailabilityClaimsAllowed);
        Assert.False(projection.StableClaimsAllowed);
        Assert.True(projection.ReviewBannerRequired);
    }

    [Fact]
    public void AuthorityManifestDigestMismatchIsRejected()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(manifest, "stable_ready");

        Assert.Throws<InvalidDataException>(() =>
            PublicReleaseAuthorityEnvelopeProjection.Project(
                authority.CurrentBytes,
                authority.SnapshotBytes,
                authority.DecisionBytes,
                manifest,
                new string('a', 64),
                authority.ManifestBytes));
    }

    [Fact]
    public void ExactDecisionBytesAreRequired()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(manifest, "stable_ready");

        Assert.Throws<InvalidDataException>(() =>
            PublicReleaseAuthorityEnvelopeProjection.Project(
                authority.CurrentBytes,
                authority.SnapshotBytes,
                Encoding.UTF8.GetBytes("{}"),
                manifest,
                Digest(authority.ManifestBytes),
                authority.ManifestBytes));
    }

    [Fact]
    public void ExactAuthorityPrimaryHeadIsNotInferredFromHeadPreference()
    {
        PublicReleaseManifestDto manifest = BuildManifest(
            BuildArtifact("linux-a-legacy", "linux", "legacy", 'd', "open_public"),
            BuildArtifact("linux-z-avalonia", "linux", "avalonia", 'e', "open_public"));
        AuthorityEnvelope authority = BuildAuthorityEnvelope(
            manifest,
            "stable_ready",
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["linux"] = "legacy"
            });

        PublicReleaseTruthProjectionDto projection = ProjectAuthority(manifest, authority);

        Assert.Equal("legacy", projection.PrimaryHeadByPlatform["linux"]);
    }

    [Fact]
    public void EmptyShelfIsValidOnlyAsReviewRequiredAndUnavailable()
    {
        PublicReleaseManifestDto manifest = BuildManifest();
        PublicReleaseTruthProjectionDto projection = ProjectAuthority(
            manifest,
            BuildAuthorityEnvelope(manifest, "review_required"));

        Assert.Empty(projection.AvailablePlatforms);
        Assert.Empty(projection.PrimaryHeadByPlatform);
        Assert.Equal(0, projection.ArtifactCount);
        Assert.Equal("unavailable", projection.DownloadAccessPosture);
        Assert.True(projection.AuthorityBound);
        Assert.False(projection.AvailabilityClaimsAllowed);
        Assert.True(projection.ReviewBannerRequired);

        AuthorityEnvelope invalidReadyAuthority = BuildAuthorityEnvelope(manifest, "stable_ready");
        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, invalidReadyAuthority));
    }

    [Fact]
    public void OversizedPublicMetadataIsRejected()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact()) with
        {
            KnownIssueSummary = new string('x', 513)
        };
        AuthorityEnvelope authority = BuildAuthorityEnvelope(manifest, "stable_ready");

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, authority));
    }

    [Fact]
    public void ReleaseDecisionMustBeTheExactDeclaredSiblingName()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(
            manifest,
            "stable_ready",
            releaseDecisionPath: "decision.json");

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, authority));
    }

    [Fact]
    public void StrictAuthoritySchemaRejectsUnknownProvenanceSentinelsAndUnsafeRoutes()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(manifest, "stable_ready");
        AuthorityEnvelope unknownField = MutateSnapshot(authority, static snapshot =>
            snapshot["generatedAt"] = "2026-07-18T00:00:00Z");
        AuthorityEnvelope wrongRepository = MutateSnapshot(authority, static snapshot =>
            snapshot["registryRepository"] = "archonmegalon/chummer6-hub-registry");
        AuthorityEnvelope sentinelRid = MutateSnapshot(authority, static snapshot =>
            snapshot["artifacts"]!.AsArray()[0]!.AsObject()["rid"] = "unknown");
        AuthorityEnvelope unsafeRoute = MutateSnapshot(authority, static snapshot =>
            snapshot["artifacts"]!.AsArray()[0]!.AsObject()["publicInstallRoute"] = "/%2e%2e/admin");

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, unknownField));
        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, wrongRepository));
        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, sentinelRid));
        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, unsafeRoute));
    }

    [Fact]
    public void NextActionsAreRequiredForReviewButMayBeEmptyWhenReady()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        AuthorityEnvelope review = MutateSnapshot(
            BuildAuthorityEnvelope(manifest, "review_required"),
            static snapshot => snapshot["nextActions"] = new JsonArray());
        AuthorityEnvelope ready = MutateSnapshot(
            BuildAuthorityEnvelope(manifest, "stable_ready"),
            static snapshot => snapshot["nextActions"] = new JsonArray());

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, review));
        Assert.Equal("stable_ready", ProjectAuthority(manifest, ready).ReleaseDecisionStatus);
    }

    [Fact]
    public void GenerationProjectionReadsTheDeclaredDecisionAsTheSnapshotSibling()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(manifest, "review_required");
        string root = Path.Combine(
            Path.GetTempPath(),
            "chummer-release-truth-" + Guid.NewGuid().ToString("N"));
        try
        {
            var inventory = new Dictionary<string, ReleaseShelfInventoryEntry>(StringComparer.Ordinal);
            AddInventoryFile(
                root,
                PublicReleaseAuthorityEnvelopeProjection.CurrentInventoryPath,
                authority.CurrentBytes,
                inventory);
            AddInventoryFile(
                root,
                PublicReleaseAuthorityEnvelopeProjection.SnapshotInventoryPath,
                authority.SnapshotBytes,
                inventory);
            AddInventoryFile(
                root,
                "release-evidence/" + PublicReleaseAuthorityEnvelopeProjection.ReleaseDecisionPath,
                authority.DecisionBytes,
                inventory);
            ReleaseShelfSnapshot shelf = ReleaseShelfSnapshot.Active(
                downloadsRoot: root,
                physicalRoot: root,
                generationId: "candidate-20260718.1",
                releaseVersion: manifest.Version,
                channel: manifest.Channel,
                publishedAt: manifest.PublishedAt,
                activatedAt: manifest.PublishedAt,
                activationReceiptId: "receipt-1",
                canonicalManifestSha256: Digest(authority.ManifestBytes),
                compatibilityManifestSha256: new string('a', 64),
                inventoryDigest: new string('b', 64),
                pointerDigest: new string('c', 64),
                inventory,
                explicitGeneration: false);

            PublicReleaseTruthProjectionDto? projection =
                PublicReleaseAuthorityEnvelopeProjection.TryProject(
                    shelf,
                    manifest,
                    Digest(authority.ManifestBytes),
                    authority.ManifestBytes,
                    out string? authoritySnapshotSha256);

            Assert.NotNull(projection);
            Assert.Equal("review_required", projection.ReleaseDecisionStatus);
            Assert.Equal(Digest(authority.DecisionBytes), projection.ReleaseDecisionSha256);
            Assert.Equal(Digest(authority.SnapshotBytes), authoritySnapshotSha256);
        }
        finally
        {
            if (Directory.Exists(root))
            {
                Directory.Delete(root, recursive: true);
            }
        }
    }

    [Theory]
    [InlineData("/")]
    [InlineData("/now")]
    [InlineData("/downloads")]
    [InlineData("/status")]
    [InlineData("/artifacts")]
    [InlineData("/progress")]
    [InlineData("/downloads/releases.json")]
    [InlineData("/downloads/g/candidate-42/releases.json")]
    [InlineData("/api/v1/public/release-truth/g/candidate-42")]
    [InlineData("/api/v1/public/weekly-pulse")]
    public async Task ReleaseFacingRoutesExposeTheSameProjectionHeader(string route)
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        PublicReleaseTruthProjectionDto projection = ProjectAuthority(
            manifest,
            BuildAuthorityEnvelope(manifest, "stable_ready"));
        var context = new DefaultHttpContext();
        context.Request.Path = route;
        var middleware = new PublicReleaseTruthProjectionMiddleware(_ => Task.CompletedTask);
        var source = new StubProjection(projection);

        await middleware.InvokeAsync(context, source);

        if (route.Contains("/g/candidate-42", StringComparison.Ordinal))
        {
            Assert.Equal("candidate-42", source.LastGenerationId);
        }

        string encoded = context.Response.Headers[
            PublicReleaseTruthProjectionMiddleware.ProjectionHeaderName].ToString();
        Assert.NotEmpty(encoded);
        string padded = encoded.PadRight(encoded.Length + ((4 - encoded.Length % 4) % 4), '=')
            .Replace('-', '+')
            .Replace('_', '/');
        PublicReleaseTruthProjectionDto? observed = JsonSerializer.Deserialize<PublicReleaseTruthProjectionDto>(
            Convert.FromBase64String(padded));
        Assert.Equal(JsonSerializer.Serialize(projection), JsonSerializer.Serialize(observed));
        Assert.Equal(
            projection.ReleaseDecisionStatus,
            context.Response.Headers[PublicReleaseTruthProjectionMiddleware.DecisionStatusHeaderName]);
        Assert.Equal(
            Digest(source.AuthoritySnapshotBytes),
            context.Response.Headers[PublicReleaseTruthProjectionMiddleware.AuthoritySnapshotSha256HeaderName]);
    }

    private static PublicReleaseTruthProjectionDto ProjectAuthority(
        PublicReleaseManifestDto manifest,
        AuthorityEnvelope authority)
        => PublicReleaseAuthorityEnvelopeProjection.Project(
            authority.CurrentBytes,
            authority.SnapshotBytes,
            authority.DecisionBytes,
            manifest,
            Digest(authority.ManifestBytes),
            authority.ManifestBytes);

    private static AuthorityEnvelope MutateSnapshot(
        AuthorityEnvelope authority,
        Action<JsonObject> mutation)
    {
        JsonObject snapshot = JsonNode.Parse(
            Encoding.UTF8.GetString(authority.SnapshotBytes.Span))!.AsObject();
        mutation(snapshot);
        ReadOnlyMemory<byte> snapshotBytes = Encoding.UTF8.GetBytes(snapshot.ToJsonString());
        JsonObject current = JsonNode.Parse(
            Encoding.UTF8.GetString(authority.CurrentBytes.Span))!.AsObject();
        current["snapshotSha256"] = Digest(snapshotBytes);
        ReadOnlyMemory<byte> currentBytes = Encoding.UTF8.GetBytes(current.ToJsonString());
        return authority with
        {
            CurrentBytes = currentBytes,
            SnapshotBytes = snapshotBytes
        };
    }

    private static AuthorityEnvelope BuildAuthorityEnvelope(
        PublicReleaseManifestDto manifest,
        string releaseDecisionStatus,
        IReadOnlyDictionary<string, string>? primaryHeads = null,
        string releaseDecisionPath = PublicReleaseAuthorityEnvelopeProjection.ReleaseDecisionPath)
    {
        ReadOnlyMemory<byte> manifestBytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
        {
            contractName = "Chummer.Hub.Registry.Contracts",
            version = manifest.Version,
            channel = manifest.Channel
        }));
        string manifestSha256 = Digest(manifestBytes);
        ReadOnlyMemory<byte> decisionBytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
        {
            contractName = "chummer.release-decision/v1",
            releaseVersion = manifest.Version,
            status = releaseDecisionStatus
        }));
        string decisionSha256 = Digest(decisionBytes);
        var artifacts = manifest.Downloads
            .OrderBy(static artifact => artifact.Id, StringComparer.Ordinal)
            .Select(static artifact => new
            {
                artifactId = artifact.Id,
                head = PublicReleaseTruthProjectionService.NormalizeToken(artifact.Head),
                platform = PublicReleaseTruthProjectionService.ResolvePlatformId(artifact),
                rid = (artifact.Rid ?? string.Empty).Trim().ToLowerInvariant(),
                arch = PublicReleaseTruthProjectionService.NormalizeToken(artifact.Arch),
                kind = "installer",
                downloadUrl = artifact.Url,
                sha256 = artifact.Sha256.Trim().ToLowerInvariant(),
                sizeBytes = artifact.SizeBytes,
                compatibilityState = "compatible",
                promotionState = "promoted",
                publicationScope = "signed-in-and-public",
                revokeState = "not_revoked",
                publicInstallRoute = $"/downloads/get/{artifact.Id}",
                installAccessClass = PublicReleaseTruthProjectionService.NormalizeToken(artifact.InstallAccessClass)
            })
            .ToArray();
        string[] availablePlatforms = artifacts
            .Select(static artifact => artifact.platform)
            .Distinct(StringComparer.Ordinal)
            .OrderBy(static platform => platform, StringComparer.Ordinal)
            .ToArray();
        var primaryHeadByPlatform = primaryHeads is null
            ? new SortedDictionary<string, string>(
                artifacts
                    .GroupBy(static artifact => artifact.platform, StringComparer.Ordinal)
                    .ToDictionary(
                        static group => group.Key,
                        static group => group.First().head,
                        StringComparer.Ordinal),
                StringComparer.Ordinal)
            : new SortedDictionary<string, string>(
                primaryHeads.ToDictionary(
                    static entry => entry.Key,
                    static entry => entry.Value,
                    StringComparer.Ordinal),
                StringComparer.Ordinal);
        string[] accessClasses = artifacts
            .Select(static artifact => artifact.installAccessClass)
            .Distinct(StringComparer.Ordinal)
            .ToArray();
        string downloadAccessPosture = accessClasses.Length switch
        {
            0 => "unavailable",
            1 => accessClasses[0],
            _ => "mixed"
        };
        byte[] snapshotBytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
        {
            authorityContract = PublicReleaseAuthorityEnvelopeProjection.AuthorityContract,
            releaseVersion = manifest.Version,
            channel = PublicReleaseTruthProjectionService.NormalizeToken(manifest.Channel),
            status = PublicReleaseTruthProjectionService.NormalizeToken(manifest.Status),
            rolloutState = PublicReleaseTruthProjectionService.NormalizeToken(manifest.RolloutState),
            supportabilityState = PublicReleaseTruthProjectionService.NormalizeToken(manifest.SupportabilityState),
            availablePlatforms,
            primaryHeadByPlatform,
            artifactCount = artifacts.Length,
            downloadAccessPosture,
            knownIssueSummary = manifest.KnownIssueSummary,
            manifestSha256,
            registryRepository = PublicReleaseAuthorityEnvelopeProjection.RegistryRepository,
            registryCommit = RegistryCommit,
            releaseDecisionStatus,
            releaseDecisionSha256 = decisionSha256,
            supportOwner = "release-operations",
            nextActions = new[] { "Verify live route convergence." },
            artifacts,
            manifestPath = PublicReleaseAuthorityEnvelopeProjection.ManifestPath,
            releaseDecisionPath
        }));
        byte[] currentBytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
        {
            releaseVersion = manifest.Version,
            snapshotSha256 = Digest(snapshotBytes),
            decisionSha256,
            status = releaseDecisionStatus
        }));
        return new(currentBytes, snapshotBytes, decisionBytes, manifestBytes);
    }

    private static PublicReleaseManifestDto BuildManifest(params PublicReleaseArtifactDto[] artifacts)
        => new(
            Version: "6.2.0",
            Channel: "public_stable",
            PublishedAt: DateTimeOffset.Parse("2026-07-18T00:00:00Z"),
            Downloads: artifacts,
            Status: "published",
            RolloutState: "public_stable",
            SupportabilityState: "gold_supported",
            KnownIssueSummary: "Known caution.");

    private static PublicReleaseArtifactDto BuildPublicArtifact()
        => BuildArtifact("windows", "windows", "avalonia", 'd', "open_public");

    private static PublicReleaseArtifactDto BuildArtifact(
        string id,
        string platform,
        string head,
        char shaCharacter,
        string installAccessClass)
        => new(
            Id: id,
            Platform: platform,
            Url: $"/downloads/{id}",
            Sha256: new string(shaCharacter, 64),
            Head: head,
            PlatformId: platform,
            Rid: platform switch
            {
                "windows" => "win-x64",
                "macos" => "osx-x64",
                _ => platform + "-x64"
            },
            Arch: "x64",
            Kind: "installer",
            SizeBytes: 1024,
            CompatibilityState: "compatible",
            InstallAccessClass: installAccessClass);

    private static string Digest(ReadOnlyMemory<byte> bytes)
        => Convert.ToHexStringLower(SHA256.HashData(bytes.Span));

    private static void AddInventoryFile(
        string root,
        string relativePath,
        ReadOnlyMemory<byte> bytes,
        IDictionary<string, ReleaseShelfInventoryEntry> inventory)
    {
        string path = Path.Combine(root, relativePath.Replace('/', Path.DirectorySeparatorChar));
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllBytes(path, bytes.ToArray());
        inventory.Add(
            relativePath,
            new ReleaseShelfInventoryEntry(relativePath, Digest(bytes), bytes.Length));
    }

    private sealed record AuthorityEnvelope(
        ReadOnlyMemory<byte> CurrentBytes,
        ReadOnlyMemory<byte> SnapshotBytes,
        ReadOnlyMemory<byte> DecisionBytes,
        ReadOnlyMemory<byte> ManifestBytes);

    private sealed class StubProjection(PublicReleaseTruthProjectionDto projection)
        : IReleaseTruthProjection
    {
        public ReadOnlyMemory<byte> AuthoritySnapshotBytes { get; } = Encoding.UTF8.GetBytes("authority-snapshot");

        public string? LastGenerationId { get; private set; }

        public PublicReleaseTruthCapture CaptureWithAuthority()
            => new(projection, Digest(AuthoritySnapshotBytes));

        public PublicReleaseTruthCapture CaptureGenerationWithAuthority(string generationId)
        {
            LastGenerationId = generationId;
            return new(projection, Digest(AuthoritySnapshotBytes));
        }

        public PublicReleaseTruthProjectionDto Capture() => projection;

        public PublicReleaseTruthProjectionDto CaptureGeneration(string generationId)
        {
            LastGenerationId = generationId;
            return projection;
        }

        public PublicReleaseTruthProjectionDto Project(
            PublicReleaseManifestDto manifest,
            string? immutableManifestSha256,
            ReadOnlyMemory<byte>? immutableAuthorityManifestBytes)
            => projection;
    }
}
