using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace Chummer.Tests;

public sealed class InternalReleaseUploadSessionHttpIntegrationTests
{
    private const string ReleaseVersion = "run-20260714-040947";
    private const string PublishedAt = "2026-07-14T04:11:58Z";
    private const string AutomationToken = "release-http-integration-token";
    private static readonly IReadOnlyList<ShelfArtifact> ShelfArtifacts =
    [
        new(
            ArtifactId: "avalonia-linux-x64-installer",
            Platform: "linux",
            PlatformId: "linux-x64",
            PlatformLabel: "Avalonia Desktop Linux x64",
            Arch: "x64",
            Rid: "linux-x64",
            Kind: "installer",
            FileName: "chummer-avalonia-linux-x64-installer.deb",
            Bytes: "linux-live"u8.ToArray(),
            SigningStatus: "not_applicable",
            NotarizationStatus: "not_applicable"),
        new(
            ArtifactId: "avalonia-win-x64-installer",
            Platform: "windows",
            PlatformId: "windows-x64",
            PlatformLabel: "Avalonia Desktop Windows x64",
            Arch: "x64",
            Rid: "win-x64",
            Kind: "installer",
            FileName: "chummer-avalonia-win-x64-installer.exe",
            Bytes: "windows-live"u8.ToArray(),
            SigningStatus: "skipped_preview",
            NotarizationStatus: "not_applicable"),
        new(
            ArtifactId: "avalonia-osx-arm64-installer",
            Platform: "macos",
            PlatformId: "macos-arm64",
            PlatformLabel: "Avalonia Desktop macOS arm64",
            Arch: "arm64",
            Rid: "osx-arm64",
            Kind: "dmg",
            FileName: "chummer-avalonia-osx-arm64-installer.dmg",
            Bytes: "mac-live"u8.ToArray(),
            SigningStatus: "skipped_preview",
            NotarizationStatus: "skipped_preview")
    ];
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    [Fact]
    public async Task StagedUploadSessionCorrectsOptimisticStaleProofInCommittedAndServedCanonicalManifest()
    {
        await using TestReleaseApp fixture = await TestReleaseApp.StartAsync();
        using HttpClient client = fixture.CreateClient();
        ReleaseUploadTicketIssueResult issuedTicket = fixture.Services
            .GetRequiredService<ReleaseUploadTicketService>()
            .Issue(new AuthenticatedHubSubject(
                SubjectId: "release-http-integration-subject",
                DisplayName: "Release Integration",
                Email: "release-integration@example.com",
                Roles: ["operator"],
                AccessToken: "test-only-upstream-token"));
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", issuedTicket.Ticket);

        using HttpResponseMessage createResponse = await client.PostAsync(
            "/api/internal/releases/upload-sessions",
            new ByteArrayContent([]));
        string createBody = await ReadSuccessBodyAsync(createResponse);
        using JsonDocument created = JsonDocument.Parse(createBody);
        string sessionId = created.RootElement.GetProperty("sessionId").GetString()
            ?? throw new InvalidDataException("upload-session response did not include sessionId.");

        await UploadFileAsync(client, sessionId, "releases.json", "application/json", BuildCompatibilityManifest());
        await UploadFileAsync(client, sessionId, "RELEASE_CHANNEL.generated.json", "application/json", BuildOptimisticStaleCanonicalManifest());
        await UploadFileAsync(client, sessionId, "release-evidence/public-promotion.json", "application/json", BuildPromotionEvidence());
        foreach (ShelfArtifact artifact in ShelfArtifacts)
        {
            await UploadFileAsync(
                client,
                sessionId,
                $"files/{artifact.FileName}",
                "application/octet-stream",
                artifact.Bytes);
            await UploadFileAsync(
                client,
                sessionId,
                $"startup-smoke/startup-smoke-avalonia-{artifact.Platform}-{artifact.Arch}.receipt.json",
                "application/json",
                BuildStartupSmokeReceipt(artifact));
        }
        IReadOnlyDictionary<string, byte[]> governedBuildProvenance = MacBuildProvenanceTestFixture.CreateFiles(
            ShelfArtifacts
                .Where(artifact => MacBuildProvenanceTestFixture.IsGovernedDesktopPlatform(artifact.Platform))
                .Select(artifact => new MacBuildProvenanceSubject(
                    artifact.ArtifactId,
                    "avalonia",
                    artifact.FileName,
                    artifact.Bytes,
                    artifact.Platform)));
        foreach ((string relativePath, byte[] bytes) in governedBuildProvenance)
        {
            await UploadFileAsync(client, sessionId, relativePath, "application/json", bytes);
        }

        using HttpResponseMessage completeResponse = await client.PostAsync(
            $"/api/internal/releases/upload-sessions/{sessionId}/complete",
            new ByteArrayContent([]));
        string firstCompletionBody = await ReadSuccessBodyAsync(completeResponse);
        AssertCredentialResponseHeaders(completeResponse);
        using JsonDocument firstCompletion = JsonDocument.Parse(firstCompletionBody);
        string activatedGenerationId = firstCompletion.RootElement.GetProperty("generationId").GetString()
            ?? throw new InvalidDataException("upload-session completion did not include generationId.");
        PublicReleaseManifestService releaseManifestService = fixture.Services
            .GetRequiredService<PublicReleaseManifestService>();
        var activatedManifest = releaseManifestService.LoadManifest(
            releaseManifestService.CaptureShelfGeneration(activatedGenerationId));
        Assert.Equal(activatedGenerationId, activatedManifest.GenerationId);
        Assert.Equal(ShelfArtifacts.Count, activatedManifest.Downloads.Count);
        Assert.Equal(
            ShelfArtifacts.Count,
            firstCompletion.RootElement.GetProperty("signedInInstallClaims").GetArrayLength());

        using HttpResponseMessage repeatedCompleteResponse = await client.PostAsync(
            $"/api/internal/releases/upload-sessions/{sessionId}/complete",
            new ByteArrayContent([]));
        string repeatedCompletionBody = await ReadSuccessBodyAsync(repeatedCompleteResponse);
        AssertCredentialResponseHeaders(repeatedCompleteResponse);
        using JsonDocument repeatedCompletion = JsonDocument.Parse(repeatedCompletionBody);
        AssertSameDurablePublication(firstCompletion.RootElement, repeatedCompletion.RootElement);
        AssertGenerationBoundInstallClaims(firstCompletion.RootElement);
        AssertGenerationBoundInstallClaims(repeatedCompletion.RootElement);
        AssertFreshInstallClaimsDiffer(firstCompletion.RootElement, repeatedCompletion.RootElement);
        await AssertInstallClaimsDownloadableAsync(client, firstCompletion.RootElement);
        await AssertInstallClaimsDownloadableAsync(client, repeatedCompletion.RootElement);

        string committedManifestPath = Path.Combine(fixture.DownloadsRoot, "RELEASE_CHANNEL.generated.json");
        Assert.True(File.Exists(committedManifestPath), $"Expected committed canonical manifest at {committedManifestPath}.");
        using (JsonDocument committed = JsonDocument.Parse(await File.ReadAllTextAsync(committedManifestPath)))
        {
            Assert.Equal(
                "passed",
                committed.RootElement.GetProperty("releaseProof").GetProperty("status").GetString());
            JsonObject committedObject = JsonNode.Parse(committed.RootElement.GetRawText())!.AsObject();
            ReleaseProofTrustEvaluation proofTrust = ReleaseProofTrustEvaluator.Validate(
                committedObject["releaseProof"] as JsonObject);
            Assert.True(
                proofTrust.IsValid,
                $"{proofTrust.Reason}; routes={committedObject["releaseProof"]?["proofRoutes"]?.ToJsonString()}");
            ReleaseProofFreshnessEvaluation proofFreshness = ReleaseProofFreshnessEvaluator.Evaluate(
                (committedObject["publicTrustMetrics"] as JsonObject)?["proofFreshness"] as JsonObject,
                committedObject["releaseProof"] as JsonObject,
                DateTimeOffset.Parse(PublishedAt),
                DateTimeOffset.UtcNow);
            Assert.Equal("stale", proofFreshness.MaterializedStatus);
            AssertReviewRequiredProjection(committed.RootElement);
        }

        using HttpResponseMessage servedResponse = await client.GetAsync("/downloads/RELEASE_CHANNEL.generated.json");
        string servedBody = await ReadSuccessBodyAsync(servedResponse);
        Assert.Equal("application/json", servedResponse.Content.Headers.ContentType?.MediaType);
        using JsonDocument served = JsonDocument.Parse(servedBody);
        AssertReviewRequiredProjection(served.RootElement);

        foreach ((string relativePath, byte[] expectedBytes) in governedBuildProvenance)
        {
            string promotedPath = Path.Combine(
                fixture.DownloadsRoot,
                relativePath.Replace('/', Path.DirectorySeparatorChar));
            Assert.True(File.Exists(promotedPath), $"Expected promoted governed proof at {promotedPath}.");
            Assert.Equal(expectedBytes, await File.ReadAllBytesAsync(promotedPath));
        }

        string retainedSessionRoot = Path.Combine(fixture.SessionRoot, sessionId);
        Assert.True(
            Directory.Exists(retainedSessionRoot),
            "The durable completion receipt must survive a lost HTTP response.");
        Assert.False(
            Directory.Exists(Path.Combine(retainedSessionRoot, "bundle")),
            "Uploaded bundle bytes should be removed after the completion receipt is durable.");
        string retainedSessionJson = await File.ReadAllTextAsync(Path.Combine(retainedSessionRoot, "session.json"));
        using JsonDocument retainedSession = JsonDocument.Parse(retainedSessionJson);
        Assert.True(retainedSession.RootElement.GetProperty("Completed").GetBoolean());
        Assert.False(retainedSession.RootElement.GetProperty("Publishing").GetBoolean());
        JsonElement retainedCompletion = retainedSession.RootElement.GetProperty("CompletionResult");
        Assert.True(
            !retainedCompletion.TryGetProperty("SignedInInstallClaims", out JsonElement retainedClaims)
            || retainedClaims.ValueKind == JsonValueKind.Null,
            "Durable completion metadata must not retain bearer install claims.");
    }

    [Fact]
    public async Task CanonicalManifestHttpEndpointFloorsOptimisticStaleProjectionWithoutMutatingSourceAndDisablesCaches()
    {
        await using TestReleaseApp fixture = await TestReleaseApp.StartAsync();
        string manifestPath = Path.Combine(fixture.DownloadsRoot, "RELEASE_CHANNEL.generated.json");
        Directory.CreateDirectory(fixture.DownloadsRoot);
        byte[] sourceBytes = BuildOptimisticStaleCanonicalManifest();
        await File.WriteAllBytesAsync(manifestPath, sourceBytes);
        using JsonDocument source = JsonDocument.Parse(sourceBytes);

        using HttpClient client = fixture.CreateClient();
        using HttpResponseMessage response = await client.GetAsync("/downloads/RELEASE_CHANNEL.generated.json");
        string responseBody = await ReadSuccessBodyAsync(response);
        using JsonDocument served = JsonDocument.Parse(responseBody);

        Assert.Equal("application/json", response.Content.Headers.ContentType?.MediaType);
        Assert.Contains("no-store", response.Headers.CacheControl?.ToString(), StringComparison.OrdinalIgnoreCase);
        Assert.Equal("no-store, max-age=0", Assert.Single(response.Headers.GetValues("CDN-Cache-Control")));
        Assert.Equal("no-store, max-age=0", Assert.Single(response.Headers.GetValues("Cloudflare-CDN-Cache-Control")));
        Assert.Equal("no-store", Assert.Single(response.Headers.GetValues("Surrogate-Control")));
        Assert.Contains("no-cache", response.Headers.Pragma.ToString(), StringComparison.OrdinalIgnoreCase);

        Assert.Equal(ReleaseVersion, served.RootElement.GetProperty("version").GetString());
        Assert.Equal(PublishedAt, served.RootElement.GetProperty("publishedAt").GetString());
        Assert.Equal("review_required", served.RootElement.GetProperty("supportabilityState").GetString());
        Assert.Equal(
            "stale",
            served.RootElement.GetProperty("publicTrustMetrics").GetProperty("proofFreshness").GetProperty("status").GetString());
        Assert.Equal(
            "review_required",
            served.RootElement.GetProperty("publicTrustMetrics").GetProperty("releaseChannel").GetProperty("supportabilityState").GetString());
        Assert.Equal(
            "blocked",
            served.RootElement.GetProperty("publicTrustMetrics").GetProperty("releaseChannel").GetProperty("posture").GetString());
        Assert.Equal(
            "review_required",
            served.RootElement.GetProperty("registryBoundaryCoverage").GetProperty("releaseChannel").GetProperty("supportabilityState").GetString());
        Assert.Equal(
            "blocked",
            served.RootElement.GetProperty("registryBoundaryCoverage").GetProperty("releaseChannel").GetProperty("publicTrustPosture").GetString());
        Assert.Equal("public_release_review_required", served.RootElement.GetProperty("rolloutState").GetString());
        Assert.Contains("stale or incomplete proof receipts", served.RootElement.GetProperty("rolloutReason").GetString(), StringComparison.Ordinal);
        Assert.Contains("review-required", served.RootElement.GetProperty("supportabilitySummary").GetString(), StringComparison.Ordinal);
        Assert.Equal(
            "public_release_review_required",
            served.RootElement.GetProperty("publicTrustMetrics").GetProperty("releaseChannel").GetProperty("rolloutState").GetString());
        Assert.Equal(
            "public_release_review_required",
            served.RootElement.GetProperty("registryBoundaryCoverage").GetProperty("releaseChannel").GetProperty("rolloutState").GetString());
        Assert.True(JsonNode.DeepEquals(
            JsonNode.Parse(source.RootElement.GetProperty("artifacts").GetRawText()),
            JsonNode.Parse(served.RootElement.GetProperty("artifacts").GetRawText())));

        PublicReleaseManifestService manifestService = fixture.Services.GetRequiredService<PublicReleaseManifestService>();
        var pageManifest = manifestService.LoadManifest();
        Assert.Equal(ReleaseVersion, pageManifest.Version);
        Assert.Equal(DateTimeOffset.Parse(PublishedAt), pageManifest.PublishedAt);
        Assert.Equal("public_release_review_required", pageManifest.RolloutState);
        Assert.Equal("review_required", pageManifest.SupportabilityState);
        Assert.True(pageManifest.PublicTrustMetrics.HasValue);
        Assert.Equal(
            "review_required",
            pageManifest.PublicTrustMetrics.Value.GetProperty("releaseChannel").GetProperty("supportabilityState").GetString());
        Assert.True(pageManifest.RegistryBoundaryCoverage.HasValue);
        Assert.Equal(
            "review_required",
            pageManifest.RegistryBoundaryCoverage.Value.GetProperty("releaseChannel").GetProperty("supportabilityState").GetString());

        Assert.Equal(sourceBytes, await File.ReadAllBytesAsync(manifestPath));
    }

    [Fact]
    public async Task CredentialBearingDownloadRoutesDisableSharedCachesAndReferrersEvenWhenRejected()
    {
        await using TestReleaseApp fixture = await TestReleaseApp.StartAsync();
        using HttpClient client = fixture.CreateClient();

        string[] rejectedRoutes =
        [
            "/downloads/g/missing-generation/install/missing-artifact?claimCode=sensitive",
            "/downloads/file/missing-artifact?claimCode=sensitive",
            "/downloads/files/missing-artifact.bin?ticket=sensitive",
            "/downloads/install/missing-artifact/payload?ticket=sensitive",
            "/downloads/install/missing-artifact/metadata?claimCode=sensitive"
        ];
        foreach (string route in rejectedRoutes)
        {
            using HttpResponseMessage response = await client.GetAsync(route);
            Assert.Contains(
                response.StatusCode,
                new[]
                {
                    HttpStatusCode.NotFound,
                    HttpStatusCode.Gone,
                    HttpStatusCode.ServiceUnavailable
                });
            AssertCredentialResponseHeaders(response);
        }
    }

    private static void AssertCredentialResponseHeaders(HttpResponseMessage response)
    {
        Assert.Contains("no-store", response.Headers.CacheControl?.ToString(), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("immutable", response.Headers.CacheControl?.ToString(), StringComparison.OrdinalIgnoreCase);
        Assert.Equal("no-store, max-age=0", Assert.Single(response.Headers.GetValues("CDN-Cache-Control")));
        Assert.Equal("no-store, max-age=0", Assert.Single(response.Headers.GetValues("Cloudflare-CDN-Cache-Control")));
        Assert.Equal("no-store", Assert.Single(response.Headers.GetValues("Surrogate-Control")));
        Assert.Equal("no-referrer", Assert.Single(response.Headers.GetValues("Referrer-Policy")));
    }

    private static void AssertSameDurablePublication(JsonElement first, JsonElement repeated)
    {
        JsonObject firstDurable = JsonNode.Parse(first.GetRawText())!.AsObject();
        JsonObject repeatedDurable = JsonNode.Parse(repeated.GetRawText())!.AsObject();
        firstDurable.Remove("signedInInstallClaims");
        repeatedDurable.Remove("signedInInstallClaims");
        Assert.True(JsonNode.DeepEquals(firstDurable, repeatedDurable));
    }

    private static void AssertGenerationBoundInstallClaims(JsonElement completion)
    {
        string generationId = completion.GetProperty("generationId").GetString()
            ?? throw new InvalidDataException("completion response did not include a generation ID.");
        string[] promotedArtifactIds = completion.GetProperty("promotedArtifactIds")
            .EnumerateArray()
            .Select(static item => item.GetString() ?? string.Empty)
            .ToArray();

        JsonElement claims = completion.GetProperty("signedInInstallClaims");
        Assert.Equal(promotedArtifactIds.Length, claims.GetArrayLength());
        foreach (JsonElement claim in claims.EnumerateArray())
        {
            string artifactId = claim.GetProperty("artifactId").GetString()
                ?? throw new InvalidDataException("install claim did not include an artifact ID.");
            string claimCode = claim.GetProperty("claimCode").GetString()
                ?? throw new InvalidDataException("install claim did not include a claim code.");
            string installDispatchUrl = claim.GetProperty("installDispatchUrl").GetString()
                ?? throw new InvalidDataException("install claim did not include an install dispatch URL.");
            Assert.Contains(artifactId, promotedArtifactIds, StringComparer.OrdinalIgnoreCase);
            Assert.True(
                installDispatchUrl.StartsWith(
                    $"/downloads/g/{Uri.EscapeDataString(generationId)}/install/{Uri.EscapeDataString(artifactId)}?",
                    StringComparison.Ordinal),
                "Install dispatch URL must bind its generation and artifact without exposing the credential URL.");
            Assert.True(
                installDispatchUrl.Contains(
                    $"claimCode={Uri.EscapeDataString(claimCode)}",
                    StringComparison.Ordinal),
                "Install dispatch URL must carry its own claim without exposing bearer values.");
        }
    }

    private static void AssertFreshInstallClaimsDiffer(JsonElement first, JsonElement repeated)
    {
        Dictionary<string, JsonElement> firstByArtifact = first.GetProperty("signedInInstallClaims")
            .EnumerateArray()
            .ToDictionary(
                static claim => claim.GetProperty("artifactId").GetString() ?? string.Empty,
                static claim => claim,
                StringComparer.OrdinalIgnoreCase);
        JsonElement repeatedClaims = repeated.GetProperty("signedInInstallClaims");
        Assert.Equal(firstByArtifact.Count, repeatedClaims.GetArrayLength());
        foreach (JsonElement repeatedClaim in repeatedClaims.EnumerateArray())
        {
            string artifactId = repeatedClaim.GetProperty("artifactId").GetString()
                ?? throw new InvalidDataException("repeated install claim did not include an artifact ID.");
            JsonElement firstClaim = firstByArtifact[artifactId];
            Assert.False(
                string.Equals(
                    firstClaim.GetProperty("claimCode").GetString(),
                    repeatedClaim.GetProperty("claimCode").GetString(),
                    StringComparison.Ordinal),
                "Repeated completion must issue a fresh claim code without exposing either value.");
            Assert.False(
                string.Equals(
                    firstClaim.GetProperty("installDispatchUrl").GetString(),
                    repeatedClaim.GetProperty("installDispatchUrl").GetString(),
                    StringComparison.Ordinal),
                "Repeated completion must issue a fresh credential URL without exposing either URL.");
        }
    }

    private static async Task AssertInstallClaimsDownloadableAsync(
        HttpClient client,
        JsonElement completion)
    {
        foreach (JsonElement claim in completion.GetProperty("signedInInstallClaims").EnumerateArray())
        {
            string installDispatchUrl = claim.GetProperty("installDispatchUrl").GetString()
                ?? throw new InvalidDataException("completion response did not include an install dispatch URL.");
            using HttpResponseMessage response = await client.GetAsync(installDispatchUrl);
            await ReadSuccessBodyAsync(response);
            AssertCredentialResponseHeaders(response);
        }
    }

    private static async Task UploadFileAsync(
        HttpClient client,
        string sessionId,
        string relativePath,
        string contentType,
        byte[] bytes)
    {
        using MultipartFormDataContent multipart = new();
        using ByteArrayContent fileContent = new(bytes);
        fileContent.Headers.ContentType = MediaTypeHeaderValue.Parse(contentType);
        multipart.Add(fileContent, "file", Path.GetFileName(relativePath));
        multipart.Add(new StringContent(relativePath), "path");

        using HttpResponseMessage response = await client.PostAsync(
            $"/api/internal/releases/upload-sessions/{sessionId}/files",
            multipart);
        await ReadSuccessBodyAsync(response);
    }

    private static async Task<string> ReadSuccessBodyAsync(HttpResponseMessage response)
    {
        string body = await response.Content.ReadAsStringAsync();
        Assert.True(
            response.IsSuccessStatusCode,
            $"Expected a successful HTTP response but received {(int)response.StatusCode} {response.StatusCode}: {body}");
        return body;
    }

    private static void AssertReviewRequiredProjection(JsonElement manifest)
    {
        Assert.Equal(ReleaseVersion, manifest.GetProperty("version").GetString());
        Assert.Equal(PublishedAt, manifest.GetProperty("publishedAt").GetString());

        JsonElement coverage = manifest.GetProperty("desktopTupleCoverage");
        Assert.True(coverage.GetProperty("complete").GetBoolean());
        Assert.Equal(0, coverage.GetProperty("missingRequiredPlatforms").GetArrayLength());
        Assert.Equal(0, coverage.GetProperty("missingRequiredPlatformHeadRidTuples").GetArrayLength());

        Assert.Equal("review_required", manifest.GetProperty("supportabilityState").GetString());
        Assert.Equal("public_release_review_required", manifest.GetProperty("rolloutState").GetString());
        Assert.Contains(
            "stale or incomplete proof receipts",
            manifest.GetProperty("rolloutReason").GetString(),
            StringComparison.Ordinal);

        JsonElement publicTrustMetrics = manifest.GetProperty("publicTrustMetrics");
        Assert.Equal("stale", publicTrustMetrics.GetProperty("proofFreshness").GetProperty("status").GetString());
        Assert.Equal(
            "review_required",
            publicTrustMetrics.GetProperty("releaseChannel").GetProperty("supportabilityState").GetString());
        Assert.Equal(
            "blocked",
            publicTrustMetrics.GetProperty("releaseChannel").GetProperty("posture").GetString());
        Assert.Equal(
            "public_release_review_required",
            publicTrustMetrics.GetProperty("releaseChannel").GetProperty("rolloutState").GetString());
        Assert.Equal(
            "review_required",
            manifest
                .GetProperty("registryBoundaryCoverage")
                .GetProperty("releaseChannel")
                .GetProperty("supportabilityState")
                .GetString());
        Assert.Equal(
            "blocked",
            manifest
                .GetProperty("registryBoundaryCoverage")
                .GetProperty("releaseChannel")
                .GetProperty("publicTrustPosture")
                .GetString());
        Assert.Equal(
            "public_release_review_required",
            manifest
                .GetProperty("registryBoundaryCoverage")
                .GetProperty("releaseChannel")
                .GetProperty("rolloutState")
                .GetString());
    }

    private static byte[] BuildCompatibilityManifest()
        => JsonSerializer.SerializeToUtf8Bytes(new
        {
            version = ReleaseVersion,
            channel = "preview",
            publishedAt = PublishedAt,
            status = "published",
            rolloutState = "public_release_review_required",
            rolloutReason = "Proof receipts require review.",
            supportabilityState = "review_required",
            supportabilitySummary = "Proof receipts require review.",
            knownIssueSummary = "Flagship readiness proof is stale.",
            fixAvailabilitySummary = "Refresh proof receipts before wider publication.",
            releaseProof = BuildReleaseProof(),
            registryBoundaryCoverage = new
            {
                releaseChannel = new
                {
                    publicationStatus = "published",
                    rolloutState = "public_release_review_required",
                    supportabilityState = "review_required"
                },
                compatibility = new
                {
                    compatibleArtifactCount = ShelfArtifacts.Count,
                    compatibleRuntimeBundleHeadCount = 0,
                    compatibleExchangeArtifactCount = 0,
                    unknownArtifactCount = 0,
                    unknownRuntimeBundleHeadCount = 0,
                    summary = "Compatibility boundary covers the complete staged Avalonia primary shelf."
                }
            },
            downloads = ShelfArtifacts.Select(artifact => new
            {
                id = artifact.ArtifactId,
                platform = artifact.PlatformLabel,
                url = $"/downloads/files/{artifact.FileName}",
                sha256 = Sha256For(artifact),
                sizeBytes = artifact.Bytes.LongLength,
                head = "avalonia",
                platformId = artifact.PlatformId,
                arch = artifact.Arch,
                rid = artifact.Rid,
                kind = artifact.Kind,
                fileName = artifact.FileName,
                installAccessClass = "account_required"
            }).ToArray()
        }, JsonOptions);

    private static byte[] BuildCanonicalManifest()
        => JsonSerializer.SerializeToUtf8Bytes(new
        {
            schemaVersion = 1,
            product = "chummer",
            channel = "preview",
            channelId = "preview",
            version = ReleaseVersion,
            publishedAt = PublishedAt,
            status = "published",
            rolloutState = "public_release_review_required",
            rolloutReason = "Proof receipts require review.",
            supportabilityState = "review_required",
            supportabilitySummary = "Proof receipts require review.",
            knownIssueSummary = "Flagship readiness proof is stale.",
            fixAvailabilitySummary = "Refresh proof receipts before wider publication.",
            releaseProof = BuildReleaseProof(),
            publicTrustMetrics = new
            {
                releaseChannel = new
                {
                    channelId = "preview",
                    posture = "preview",
                    publicationStatus = "published",
                    rolloutState = "public_release_review_required",
                    supportabilityState = "review_required",
                    summary = "The preview requires proof review."
                },
                proofFreshness = BuildStaleProofFreshness()
            },
            registryBoundaryCoverage = new
            {
                releaseChannel = new
                {
                    publicationStatus = "published",
                    rolloutState = "public_release_review_required",
                    supportabilityState = "review_required"
                },
                compatibility = new
                {
                    compatibleArtifactCount = ShelfArtifacts.Count,
                    compatibleRuntimeBundleHeadCount = 0,
                    compatibleExchangeArtifactCount = 0,
                    unknownArtifactCount = 0,
                    unknownRuntimeBundleHeadCount = 0,
                    summary = "Compatibility boundary covers the complete staged Avalonia primary shelf."
                }
            },
            artifacts = ShelfArtifacts.Select(artifact => new
            {
                artifactId = artifact.ArtifactId,
                head = "avalonia",
                platform = artifact.Platform,
                arch = artifact.Arch,
                rid = artifact.Rid,
                kind = artifact.Kind,
                fileName = artifact.FileName,
                downloadUrl = $"/downloads/files/{artifact.FileName}",
                sha256 = Sha256For(artifact),
                sizeBytes = artifact.Bytes.LongLength,
                platformLabel = artifact.PlatformLabel,
                installAccessClass = "account_required"
            }).ToArray()
        }, JsonOptions);

    private static byte[] BuildOptimisticStaleCanonicalManifest()
    {
        JsonObject manifest = JsonNode.Parse(System.Text.Encoding.UTF8.GetString(BuildCanonicalManifest()))!.AsObject();
        manifest["rolloutState"] = "promoted_preview";
        manifest["rolloutReason"] = "Current release shelf passed the local release run before publication.";
        manifest["supportabilityState"] = "preview_supported";
        manifest["supportabilitySummary"] = "Current preview release is supported on the promoted routes.";
        manifest["knownIssueSummary"] = "Preview caveats still apply.";
        manifest["fixAvailabilitySummary"] = "The published preview is available now.";

        JsonObject publicReleaseChannel = manifest["publicTrustMetrics"]!["releaseChannel"]!.AsObject();
        publicReleaseChannel["posture"] = "preview";
        publicReleaseChannel["rolloutState"] = "promoted_preview";
        publicReleaseChannel["supportabilityState"] = "preview_supported";
        publicReleaseChannel["summary"] = "The current preview is supported.";

        JsonObject registryReleaseChannel = manifest["registryBoundaryCoverage"]!["releaseChannel"]!.AsObject();
        registryReleaseChannel["publicTrustPosture"] = "preview";
        registryReleaseChannel["rolloutState"] = "promoted_preview";
        registryReleaseChannel["supportabilityState"] = "preview_supported";
        registryReleaseChannel["summary"] = "Registry truth reports a supported preview.";

        return JsonSerializer.SerializeToUtf8Bytes(manifest, JsonOptions);
    }

    private static JsonObject BuildReleaseProof()
        => ReleaseProofEvidenceTestData.CreateReleaseProof(
            DateTimeOffset.Parse(PublishedAt).AddMinutes(-5),
            ShelfArtifacts.Select(artifact => $"/downloads/install/{artifact.ArtifactId}"));

    private static JsonObject BuildStaleProofFreshness()
    {
        JsonObject facts = ReleaseProofEvidenceTestData.CreateFreshnessFacts(
            BuildReleaseProof(),
            DateTimeOffset.Parse(PublishedAt));
        facts["status"] = "stale";
        facts["summary"] = "Flagship readiness proof is stale.";
        return facts;
    }

    private static byte[] BuildPromotionEvidence()
        => JsonSerializer.SerializeToUtf8Bytes(new
        {
            contractName = "chummer.run.desktop_release_publication",
            generatedAt = PublishedAt,
            artifacts = ShelfArtifacts.Select(artifact => new
            {
                artifactId = artifact.ArtifactId,
                fileName = artifact.FileName,
                platform = artifact.Platform,
                promotionStatus = "pass",
                startupSmokeStatus = "pass",
                signingStatus = artifact.SigningStatus,
                notarizationStatus = artifact.NotarizationStatus
            }).ToArray()
        }, JsonOptions);

    private static byte[] BuildStartupSmokeReceipt(ShelfArtifact artifact)
    {
        string recordedAtUtc = DateTimeOffset.UtcNow.ToString("O");
        bool isWindows = string.Equals(artifact.Platform, "windows", StringComparison.OrdinalIgnoreCase);
        return JsonSerializer.SerializeToUtf8Bytes(new
        {
            status = "pass",
            headId = "avalonia",
            version = ReleaseVersion,
            releaseVersion = ReleaseVersion,
            channel = "preview",
            channelId = "preview",
            platform = artifact.Platform,
            arch = artifact.Arch,
            rid = artifact.Rid,
            readyCheckpoint = "pre_ui_event_loop",
            hostClass = artifact.Platform.ToLowerInvariant() switch
            {
                "windows" => $"windows-{artifact.Arch}-host",
                "macos" => $"local-osx-{artifact.Arch}",
                _ => $"linux-{artifact.Arch}-host"
            },
            operatingSystem = artifact.Platform.ToLowerInvariant() switch
            {
                "windows" => "Microsoft Windows 11",
                "macos" => "macOS 15",
                _ => "Linux"
            },
            artifactDigest = $"sha256:{Sha256For(artifact)}",
            artifactId = artifact.ArtifactId,
            artifactFileName = artifact.FileName,
            fileName = artifact.FileName,
            artifactPath = $"files/{artifact.FileName}",
            artifactRelativePath = $"files/{artifact.FileName}",
            startedAtUtc = recordedAtUtc,
            recordedAtUtc,
            completedAtUtc = recordedAtUtc,
            sourceUpdatedAtUtc = recordedAtUtc,
            executionEnvironment = isWindows ? "native_windows" : null,
            nativeHostEvidence = isWindows
                ? new
                {
                    contractName = "chummer6-ui.native_windows_host_evidence",
                    status = "verified",
                    isNativeWindows = true,
                    hostPlatform = "windows",
                    hostKernel = "Windows_NT",
                    runner = "powershell.exe",
                    evidenceSource = "powershell_runtime_os_probe"
                }
                : null
        }, JsonOptions);
    }

    private static string Sha256For(ShelfArtifact artifact)
        => Convert.ToHexString(SHA256.HashData(artifact.Bytes)).ToLowerInvariant();

    private sealed record ShelfArtifact(
        string ArtifactId,
        string Platform,
        string PlatformId,
        string PlatformLabel,
        string Arch,
        string Rid,
        string Kind,
        string FileName,
        byte[] Bytes,
        string SigningStatus,
        string NotarizationStatus);

    private sealed class TestReleaseApp : IAsyncDisposable
    {
        private readonly WebApplication _app;
        private readonly string _root;

        private TestReleaseApp(WebApplication app, string root, string downloadsRoot)
        {
            _app = app;
            _root = root;
            DownloadsRoot = downloadsRoot;
        }

        public string DownloadsRoot { get; }

        public string SessionRoot => Path.Combine(_root, "sessions");

        public IServiceProvider Services => _app.Services;

        public static async Task<TestReleaseApp> StartAsync()
        {
            string root = Path.Combine(Path.GetTempPath(), "chummer-release-upload-http-tests", Guid.NewGuid().ToString("N"));
            string downloadsRoot = Path.Combine(root, "downloads");
            string localProofPath = Path.Combine(root, "local-release-proof.json");
            Directory.CreateDirectory(root);
            Directory.CreateDirectory(downloadsRoot);
            await File.WriteAllTextAsync(
                localProofPath,
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contract_name"] = "chummer6-hub.local_release_proof",
                    ["status"] = "passed",
                    ["generated_at"] = DateTimeOffset.UtcNow.ToString("O"),
                    ["proof_routes"] = Array.Empty<string>(),
                    ["proof_receipts"] = ImportRouteParityProofGuardService.RequiredDirectProofReceiptIds
                        .Select(receiptId => new Dictionary<string, object?>
                        {
                            ["receipt_id"] = receiptId,
                            ["package_id"] = "http-integration-isolation",
                            ["summary"] = "Isolated current import-route proof.",
                            ["routes"] = Array.Empty<string>()
                        })
                        .ToArray()
                }));

            WebApplicationBuilder builder = WebApplication.CreateBuilder();
            builder.WebHost.ConfigureKestrel(options => options.Listen(IPAddress.Loopback, 0));
            builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["FLEET_INTERNAL_API_TOKEN"] = AutomationToken,
                ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = downloadsRoot,
                ["CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"] = Path.Combine(root, "sessions"),
                ["CHUMMER_RELEASE_UPLOAD_MIN_FREE_BYTES"] = "0",
                ["CHUMMER_RELEASE_UPLOAD_MIN_FREE_FRACTION"] = "0",
                ["CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED"] = "false",
                ["CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED"] = "true",
                ["GOOGLE_OIDC_REDIRECT_URI"] = "https://chummer.run/auth/google/callback",
                ["CHUMMER_PUBLIC_CANON_ROOT"] = Path.Combine(root, "canon"),
                ["CHUMMER_PUBLIC_FLAGSHIP_READINESS_FILE"] = Path.Combine(root, "flagship-readiness-not-present.json"),
                ["CHUMMER_PUBLIC_FINAL_GOLD_JANITOR_FILE"] = Path.Combine(root, "final-gold-not-present.json"),
                ["CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE"] = localProofPath,
                ["CHUMMER_PUBLIC_LOCAL_RELEASE_PROOF_FILE"] = localProofPath,
                ["CHUMMER_RELEASE_REGISTRY_CURRENT_URL"] = string.Empty,
                ["CHUMMER_HUB_REGISTRY_BASE_URL"] = string.Empty,
                ["CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS"] = string.Empty,
                ["CHUMMER_RELEASE_DISABLED_ARTIFACT_IDS"] = string.Empty,
                ["CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS"] = "0",
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(root, "community.json"),
                ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(root, "install-linking.json")
            });

            builder.Services
                .AddControllers()
                .AddApplicationPart(typeof(InternalReleaseBundlesController).Assembly);
            builder.Services.AddDataProtection()
                .SetApplicationName("Chummer.ReleaseUpload.HttpIntegrationTests")
                .PersistKeysToFileSystem(new DirectoryInfo(Path.Combine(root, "keys")));
            ReleaseUploadQuotaOptions uploadOptions =
                ReleaseUploadQuotaOptions.FromConfiguration(builder.Configuration);
            builder.Services.AddSingleton(uploadOptions);
            builder.Services.AddSingleton<ReleaseBundlePromotionService>();
            builder.Services.AddSingleton<ReleaseBundleUploadSessionService>();
            builder.Services.AddSingleton<ReleaseUploadTicketService>();
            builder.Services.AddSingleton<ReleaseUploadAuthorizationEvaluator>();
            builder.Services.AddSingleton<ReleaseUploadAdmissionService>();
            builder.Services.AddSingleton<PublicReleaseManifestService>();
            builder.Services.AddSingleton<PublicCanonFileLoader>();
            builder.Services.AddSingleton<ReleaseSelectionService>();
            builder.Services.AddSingleton<WindowsProofInstallerService>();
            builder.Services.AddSingleton<AurPackageCatalogService>();
            builder.Services.AddSingleton<CommunityStore>();
            builder.Services.AddSingleton<AccountService>();
            builder.Services.AddSingleton<InstallLinkingStore>();
            builder.Services.AddSingleton<InstallLinkingService>();
            builder.Services.AddSingleton<InstallBootstrapTicketService>();
            builder.Services.AddSingleton<HubIdentitySubjectCache>();
            builder.Services.AddHttpClient<HubIdentityClient>();

            WebApplication app = builder.Build();
            app.UseMiddleware<ReleaseUploadRequestGateMiddleware>();
            app.MapControllers();
            try
            {
                await app.StartAsync();
                return new TestReleaseApp(app, root, downloadsRoot);
            }
            catch
            {
                await app.DisposeAsync();
                DeleteOwnedTestRoot(root);

                throw;
            }
        }

        public HttpClient CreateClient()
        {
            IServer server = _app.Services.GetRequiredService<IServer>();
            IServerAddressesFeature addresses = server.Features.Get<IServerAddressesFeature>()
                ?? throw new InvalidOperationException("Kestrel did not expose a bound address.");
            return new HttpClient
            {
                BaseAddress = new Uri(addresses.Addresses.Single())
            };
        }

        public async ValueTask DisposeAsync()
        {
            await _app.StopAsync();
            await _app.DisposeAsync();
            DeleteOwnedTestRoot(_root);
        }

        private static void DeleteOwnedTestRoot(string root)
        {
            if (!Directory.Exists(root))
            {
                return;
            }

            RestoreOwnerWriteAccess(root, isDirectory: true);
            Directory.Delete(root, recursive: true);
        }

        private static void RestoreOwnerWriteAccess(string path, bool isDirectory)
        {
            FileAttributes attributes = File.GetAttributes(path);
            if ((attributes & FileAttributes.ReadOnly) != 0)
            {
                File.SetAttributes(path, attributes & ~FileAttributes.ReadOnly);
            }

            if (!OperatingSystem.IsWindows())
            {
                UnixFileMode ownerAccess = UnixFileMode.UserRead | UnixFileMode.UserWrite;
                if (isDirectory)
                {
                    ownerAccess |= UnixFileMode.UserExecute;
                }

                File.SetUnixFileMode(path, File.GetUnixFileMode(path) | ownerAccess);
            }

            if (!isDirectory)
            {
                return;
            }

            foreach (string entry in Directory.EnumerateFileSystemEntries(path))
            {
                FileAttributes entryAttributes = File.GetAttributes(entry);
                if ((entryAttributes & FileAttributes.ReparsePoint) != 0)
                {
                    continue;
                }

                RestoreOwnerWriteAccess(
                    entry,
                    (entryAttributes & FileAttributes.Directory) != 0);
            }
        }
    }
}
