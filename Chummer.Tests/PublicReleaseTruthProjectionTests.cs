using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicReleaseTruthProjectionTests
{
    private const string RegistryCommit = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    private const string ReleaseScopeDecisionSha256 =
        "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee";

    [Fact]
    public void ProjectionPublishesTheCompleteDeterministicConvergenceContract()
    {
        PublicReleaseManifestDto manifest = BuildManifest(
            BuildArtifact("windows", "windows", "avalonia", 'd', "open_public"),
            BuildArtifact("linux-primary", "linux", "avalonia", 'f', "account_required"));
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
        Assert.Equal(2, projection.ArtifactCount);
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
                     "releaseDecisionSha256", "releaseScopeDecisionSha256"
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
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(manifest, "approved");

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, authority));
    }

    [Fact]
    public void ReviewRequiredKeepsArtifactProjectionButWithholdsOptimisticClaims()
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact());
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
        Assert.False(projection.ReviewRequiredPublicByteHandoffsAllowed);
    }

    [Fact]
    public void ScopeBoundPublishedOpenPublicReviewAllowsOnlyByteHandoffClaims()
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact());
        PublicReleaseTruthProjectionDto projection = ProjectAuthority(
            manifest,
            BuildAuthorityEnvelope(
                manifest,
                "review_required",
                publicByteHandoff: true));

        Assert.Equal(ReleaseScopeDecisionSha256, projection.ReleaseScopeDecisionSha256);
        Assert.True(projection.AuthorityBound);
        Assert.True(projection.ReviewRequiredPublicByteHandoffsAllowed);
        Assert.False(projection.AvailabilityClaimsAllowed);
        Assert.False(projection.StableClaimsAllowed);
        Assert.True(projection.ReviewBannerRequired);
    }

    [Theory]
    [InlineData("account_recommended")]
    [InlineData("account_required")]
    public void ProtectedReviewShelfNeverAllowsPublicByteHandoffs(string accessClass)
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(
            BuildArtifact("windows", "windows", "avalonia", 'd', accessClass));
        PublicReleaseTruthProjectionDto projection = ProjectAuthority(
            manifest,
            BuildAuthorityEnvelope(manifest, "review_required"));

        Assert.False(projection.ReviewRequiredPublicByteHandoffsAllowed);
        Assert.False(projection.AvailabilityClaimsAllowed);
    }

    [Fact]
    public void MixedReviewShelfNeverAllowsPublicByteHandoffs()
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(
            BuildPublicArtifact(),
            BuildArtifact("linux", "linux", "avalonia", 'f', "account_required"));
        PublicReleaseTruthProjectionDto projection = ProjectAuthority(
            manifest,
            BuildAuthorityEnvelope(manifest, "review_required"));

        Assert.Equal("mixed", projection.DownloadAccessPosture);
        Assert.False(projection.ReviewRequiredPublicByteHandoffsAllowed);
        Assert.False(projection.AvailabilityClaimsAllowed);
    }

    [Theory]
    [InlineData("status", "revoked")]
    [InlineData("rollout", "revoked")]
    [InlineData("rollout", "release_review_required")]
    [InlineData("supportability", "unsupported")]
    [InlineData("channel", "public_stable")]
    public void NonCanonicalOrRevokedReviewPostureNeverAllowsPublicByteHandoffs(
        string field,
        string value)
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact()) with
        {
            Channel = field == "channel" ? value : "preview",
            Status = field == "status" ? value : "published",
            RolloutState = field == "rollout" ? value : "public_release_review_required",
            SupportabilityState = field == "supportability" ? value : "review_required"
        };
        Assert.Throws<InvalidDataException>(() =>
            ProjectAuthority(
                manifest,
                BuildAuthorityEnvelope(
                    manifest,
                    "review_required",
                    publicByteHandoff: true)));
    }

    [Fact]
    public void PreviewDecisionRequiresAnAuthorityBoundReleaseScopeDigest()
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(
            manifest,
            "review_required",
            publicByteHandoff: true);
        JsonObject missing = JsonNode.Parse(
            Encoding.UTF8.GetString(authority.DecisionBytes.Span))!.AsObject();
        missing.Remove("releaseScopeDecisionSha256");
        AuthorityEnvelope missingAuthority = RebindDecision(
            authority,
            Encoding.UTF8.GetBytes(missing.ToJsonString()));
        JsonObject invalid = JsonNode.Parse(
            Encoding.UTF8.GetString(authority.DecisionBytes.Span))!.AsObject();
        invalid["releaseScopeDecisionSha256"] = new string('E', 64);
        AuthorityEnvelope invalidAuthority = RebindDecision(
            authority,
            Encoding.UTF8.GetBytes(invalid.ToJsonString()));

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, missingAuthority));
        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, invalidAuthority));
    }

    [Fact]
    public void ScopeDigestMutationWithoutEnvelopeRebindingIsRejected()
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(
            manifest,
            "review_required",
            publicByteHandoff: true);
        JsonObject decision = JsonNode.Parse(
            Encoding.UTF8.GetString(authority.DecisionBytes.Span))!.AsObject();
        decision["releaseScopeDecisionSha256"] = new string('f', 64);

        Assert.Throws<InvalidDataException>(() =>
            PublicReleaseAuthorityEnvelopeProjection.Project(
                authority.CurrentBytes,
                authority.SnapshotBytes,
                Encoding.UTF8.GetBytes(decision.ToJsonString()),
                manifest,
                Digest(authority.ManifestBytes),
                authority.ManifestBytes));
    }

    [Theory]
    [InlineData("contractName", "chummer.public-preview-byte-handoff/v2")]
    [InlineData("status", "review_required")]
    [InlineData("sourcePublicationState", "published")]
    [InlineData("releaseScopeDecisionSha256", "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff")]
    [InlineData("artifactId", "other-installer")]
    [InlineData("head", "blazor-desktop")]
    [InlineData("platform", "linux")]
    [InlineData("rid", "win-arm64")]
    [InlineData("arch", "arm64")]
    [InlineData("sha256", "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff")]
    [InlineData("artifactAccessClass", "account_required")]
    [InlineData("signingRequirement", "signed")]
    [InlineData("downloadUrl", "/downloads/files/other-installer.exe")]
    [InlineData("publicInstallRoute", "/downloads/get/other-installer")]
    public void V2ArtifactHandoffMustExactlyMatchScopeAndSnapshotArtifact(
        string field,
        string value)
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(
            manifest,
            "review_required",
            publicByteHandoff: true);
        JsonObject decision = JsonNode.Parse(
            Encoding.UTF8.GetString(authority.DecisionBytes.Span))!.AsObject();
        decision["artifactHandoff"]!.AsObject()[field] = value;
        AuthorityEnvelope rebound = RebindDecision(
            authority,
            Encoding.UTF8.GetBytes(decision.ToJsonString()));

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, rebound));
    }

    [Theory]
    [InlineData("/downloads/g/../files/installer.exe")]
    [InlineData("/downloads/g/%2e%2e/files/installer.exe")]
    [InlineData("/downloads/g/generation%2fescape/files/installer.exe")]
    [InlineData("/downloads/g/generation/files/%2e%2e")]
    [InlineData("/downloads/g/generation/files/installer%5cexe")]
    [InlineData("/downloads/g/generation/files/installer.exe?ticket=secret")]
    [InlineData("/downloads/g/generation/files/installer.exe#fragment")]
    [InlineData("/downloads/g/generation/files/nested/installer.exe")]
    [InlineData("https://user@chummer.run/downloads/g/generation/files/installer.exe")]
    [InlineData("//chummer.run/downloads/g/generation/files/installer.exe")]
    public void V2ArtifactHandoffRejectsUnsafeDownloadUrlsEvenWhenAuthorityMatches(
        string downloadUrl)
    {
        PublicReleaseArtifactDto artifact = BuildPublicArtifact() with
        {
            Url = downloadUrl
        };
        PublicReleaseManifestDto manifest = BuildReviewManifest(artifact);

        Assert.Throws<InvalidDataException>(() =>
            ProjectAuthority(
                manifest,
                BuildAuthorityEnvelope(
                    manifest,
                    "review_required",
                    publicByteHandoff: true)));
    }

    [Theory]
    [InlineData("/downloads/install/../windows")]
    [InlineData("/downloads/install/%2e%2e")]
    [InlineData("/downloads/install/windows?ticket=secret")]
    [InlineData("/downloads/install/windows#fragment")]
    [InlineData("https://user@chummer.run/downloads/install/windows")]
    public void V2ArtifactHandoffRejectsUnsafeInstallRoutesEvenWhenSnapshotMatches(
        string publicInstallRoute)
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = MutateSnapshot(
            BuildAuthorityEnvelope(
                manifest,
                "review_required",
                publicByteHandoff: true),
            snapshot => snapshot["artifacts"]!.AsArray()[0]!.AsObject()[
                "publicInstallRoute"] = publicInstallRoute);
        JsonObject decision = JsonNode.Parse(
            Encoding.UTF8.GetString(authority.DecisionBytes.Span))!.AsObject();
        decision["artifactHandoff"]!.AsObject()["publicInstallRoute"] = publicInstallRoute;
        AuthorityEnvelope rebound = RebindDecision(
            authority,
            Encoding.UTF8.GetBytes(decision.ToJsonString()));

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, rebound));
    }

    [Fact]
    public void V2ArtifactHandoffRejectsMissingUnknownAndWrongSizedBindings()
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(
            manifest,
            "review_required",
            publicByteHandoff: true);

        AuthorityEnvelope Mutate(Action<JsonObject> mutation)
        {
            JsonObject decision = JsonNode.Parse(
                Encoding.UTF8.GetString(authority.DecisionBytes.Span))!.AsObject();
            mutation(decision["artifactHandoff"]!.AsObject());
            return RebindDecision(
                authority,
                Encoding.UTF8.GetBytes(decision.ToJsonString()));
        }

        Assert.Throws<InvalidDataException>(() =>
            ProjectAuthority(manifest, Mutate(handoff => handoff.Remove("artifactId"))));
        Assert.Throws<InvalidDataException>(() =>
            ProjectAuthority(manifest, Mutate(handoff => handoff["unexpected"] = "value")));
        Assert.Throws<InvalidDataException>(() =>
            ProjectAuthority(manifest, Mutate(handoff => handoff["sizeBytes"] = 1025)));
    }

    [Fact]
    public void AuthorityManifestDigestMismatchIsRejected()
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact());
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
    public void ArbitraryDecisionIsRejectedAfterEveryAuthorityDigestIsRebound()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = RebindDecision(
            BuildAuthorityEnvelope(manifest, "stable_ready"),
            Encoding.UTF8.GetBytes("{}"));

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, authority));
    }

    [Fact]
    public void LegacyDecisionContractIsRejectedAfterEveryAuthorityDigestIsRebound()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        byte[] legacyDecision = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
        {
            contractName = "chummer.release-decision/v1",
            releaseVersion = manifest.Version,
            status = "stable_ready"
        }));
        AuthorityEnvelope authority = RebindDecision(
            BuildAuthorityEnvelope(manifest, "stable_ready"),
            legacyDecision);

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, authority));
    }

    [Fact]
    public void StableDecisionNestedManifestDriftIsRejectedAfterDigestClosure()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(manifest, "stable_ready");
        JsonObject decision = JsonNode.Parse(Encoding.UTF8.GetString(authority.DecisionBytes.Span))!.AsObject();
        decision["live_release"]!.AsObject()["manifest_sha256"] = new string('9', 64);

        authority = RebindDecision(authority, Encoding.UTF8.GetBytes(decision.ToJsonString()));

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, authority));
    }

    [Fact]
    public void StableDecisionReviewVerdictIsRejectedAfterDigestClosure()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(manifest, "stable_ready");
        JsonObject decision = JsonNode.Parse(Encoding.UTF8.GetString(authority.DecisionBytes.Span))!.AsObject();
        decision["verdict"] = "PUBLIC_RELEASE_REVIEW_REQUIRED";

        authority = RebindDecision(authority, Encoding.UTF8.GetBytes(decision.ToJsonString()));

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, authority));
    }

    [Fact]
    public void PreviewReadyDecisionCannotCarryBlockingFindingsAfterDigestClosure()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(manifest, "preview_ready");
        JsonObject decision = JsonNode.Parse(Encoding.UTF8.GetString(authority.DecisionBytes.Span))!.AsObject();
        decision["blockingFindings"] = new JsonArray(new JsonObject
        {
            ["id"] = "preview_1",
            ["severity"] = "release_truth",
            ["summary"] = "Contradictory blocker."
        });

        authority = RebindDecision(authority, Encoding.UTF8.GetBytes(decision.ToJsonString()));

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, authority));
    }

    [Fact]
    public void StableProofRowsRejectUnknownFieldsAfterDigestClosure()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(manifest, "stable_ready");
        JsonObject decision = JsonNode.Parse(Encoding.UTF8.GetString(authority.DecisionBytes.Span))!.AsObject();
        decision["proof_inputs"]!.AsArray()[0]!.AsObject()["fabricated"] = true;

        authority = RebindDecision(authority, Encoding.UTF8.GetBytes(decision.ToJsonString()));

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, authority));
    }

    [Fact]
    public void StableLiveAndAuthorityDecisionDigestsMustAgreeAfterDigestClosure()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(manifest, "stable_ready");
        JsonObject decision = JsonNode.Parse(Encoding.UTF8.GetString(authority.DecisionBytes.Span))!.AsObject();
        decision["live_release"]!.AsObject()["release_decision_sha256"] = new string('9', 64);

        authority = RebindDecision(authority, Encoding.UTF8.GetBytes(decision.ToJsonString()));

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, authority));
    }

    [Fact]
    public void CaseShadowedDecisionPropertyIsRejectedAfterDigestClosure()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        AuthorityEnvelope authority = BuildAuthorityEnvelope(manifest, "review_required");
        JsonObject decision = JsonNode.Parse(Encoding.UTF8.GetString(authority.DecisionBytes.Span))!.AsObject();
        decision["Status"] = "review_required";

        authority = RebindDecision(authority, Encoding.UTF8.GetBytes(decision.ToJsonString()));

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(manifest, authority));
    }

    [Fact]
    public void ExactAuthorityPrimaryHeadIsNotInferredFromHeadPreference()
    {
        PublicReleaseManifestDto manifest = BuildManifest(
            BuildArtifact("linux-a-legacy", "linux", "legacy", 'd', "open_public"),
            BuildArtifact("linux-z-avalonia", "linux", "avalonia", 'e', "open_public"));
        AuthorityEnvelope authority = BuildAuthorityEnvelope(
            manifest,
            "preview_ready",
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
    public void AuthorityArtifactRoutesMustMatchTheirAccessClass()
    {
        PublicReleaseManifestDto openManifest = BuildManifest(
            BuildArtifact("windows-open", "windows", "avalonia", 'd', "open_public"));
        AuthorityEnvelope openRoutesCollapsed = MutateSnapshot(
            BuildAuthorityEnvelope(openManifest, "review_required"),
            static snapshot =>
            {
                JsonObject artifact = snapshot["artifacts"]!.AsArray()[0]!.AsObject();
                artifact["publicInstallRoute"] = artifact["downloadUrl"]!.GetValue<string>();
            });

        PublicReleaseManifestDto protectedManifest = BuildManifest(
            BuildArtifact("linux-protected", "linux", "avalonia", 'e', "account_required"));
        AuthorityEnvelope protectedAuthority = BuildAuthorityEnvelope(
            protectedManifest,
            "review_required");
        AuthorityEnvelope protectedRoutesSplit = MutateSnapshot(
            protectedAuthority,
            static snapshot => snapshot["artifacts"]!.AsArray()[0]!.AsObject()["publicInstallRoute"] =
                "/downloads/get/different-artifact");

        Assert.Throws<InvalidDataException>(() => ProjectAuthority(openManifest, openRoutesCollapsed));
        Assert.Equal(
            "account_required",
            ProjectAuthority(protectedManifest, protectedAuthority).DownloadAccessPosture);
        Assert.Throws<InvalidDataException>(() => ProjectAuthority(protectedManifest, protectedRoutesSplit));
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
    [InlineData("/Now/")]
    [InlineData("/now/concierge")]
    [InlineData("/NOW/CONCIERGE/install/")]
    [InlineData("/downloads")]
    [InlineData("/downloads/concierge")]
    [InlineData("/downloads/install/example-installer")]
    [InlineData("/downloads/install/example-installer/bootstrap.sh")]
    [InlineData("/DOWNLOADS/INSTALL/example-installer/")]
    [InlineData("/status")]
    [InlineData("/artifacts")]
    [InlineData("/progress")]
    [InlineData("/help")]
    [InlineData("/HELP/")]
    [InlineData("/downloads/releases.json")]
    [InlineData("/downloads/g/candidate-42/releases.json")]
    [InlineData("/downloads/g/candidate-42/install/example-installer")]
    [InlineData("/api/v1/public/release-truth/g/candidate-42")]
    [InlineData("/api/v1/public/weekly-pulse")]
    [InlineData("/API/V1/INSTALL-LINKING/CONTINUATION/")]
    [InlineData("/api/v1/install-linking/continuation/support")]
    [InlineData("/api/v1/install-linking/continuation/update")]
    [InlineData("/api/v1/install-linking/continuation/rollback/")]
    public async Task ReleaseFacingRoutesExposeTheSameProjectionHeader(string route)
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        PublicReleaseTruthProjectionDto projection = ProjectAuthority(
            manifest,
            BuildAuthorityEnvelope(manifest, "stable_ready"));
        var context = new DefaultHttpContext();
        context.Request.Path = route;
        var source = new StubProjection(projection);
        using var responseBody = new MemoryStream();
        context.Response.Body = responseBody;

        var bodyMiddleware = new PublicReleaseTruthProjectionMiddleware(async responseContext =>
        {
            responseContext.Response.ContentType = "application/json";
            await JsonSerializer.SerializeAsync(responseContext.Response.Body, projection);
        });
        await InvokeMiddlewareAsync(bodyMiddleware, context, source);

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
        responseBody.Position = 0;
        PublicReleaseTruthProjectionDto? observedBody = await JsonSerializer.DeserializeAsync<PublicReleaseTruthProjectionDto>(responseBody);
        Assert.Equal(JsonSerializer.Serialize(projection), JsonSerializer.Serialize(observedBody));
        Assert.Equal(
            projection.ReleaseDecisionStatus,
            context.Response.Headers[PublicReleaseTruthProjectionMiddleware.DecisionStatusHeaderName]);
        Assert.Equal(
            Digest(source.AuthoritySnapshotBytes),
            context.Response.Headers[PublicReleaseTruthProjectionMiddleware.AuthoritySnapshotSha256HeaderName]);
    }

    [Fact]
    public async Task StableReadyPublicInstallDispatchBypassesUnreadyDurableStoreGate()
    {
        PublicReleaseManifestDto manifest = BuildManifest(BuildPublicArtifact());
        PublicReleaseTruthProjectionDto projection = ProjectAuthority(
            manifest,
            BuildAuthorityEnvelope(manifest, "stable_ready"));
        var context = new DefaultHttpContext();
        context.Request.Path = "/downloads/install/windows";
        context.Request.Method = HttpMethods.Get;
        bool controllerInvoked = false;
        var admission = new InstallLinkingRequestAdmissionMiddleware(responseContext =>
        {
            controllerInvoked = true;
            responseContext.Response.Redirect(
                "/downloads/get/windows",
                permanent: false);
            return Task.CompletedTask;
        });
        var releaseTruth = new PublicReleaseTruthProjectionMiddleware(
            responseContext => admission.InvokeAsync(
                responseContext,
                new UnavailableInstallLinkingReadinessProbe()));

        await InvokeMiddlewareAsync(
            releaseTruth,
            context,
            new StubProjection(projection));

        Assert.True(controllerInvoked);
        Assert.Equal(StatusCodes.Status302Found, context.Response.StatusCode);
        Assert.Equal(
            "/downloads/get/windows",
            context.Response.Headers.Location.ToString());
        Assert.Equal(
            "stable_ready",
            context.Response.Headers[
                PublicReleaseTruthProjectionMiddleware.DecisionStatusHeaderName]);
    }

    [Theory]
    [InlineData("/downloads/get/example-installer")]
    [InlineData("/downloads/file/example-installer")]
    [InlineData("/downloads/files/example-installer.exe")]
    [InlineData("/downloads/install/example-installer")]
    [InlineData("/downloads/install/example-installer/bootstrap.sh")]
    [InlineData("/downloads/g/candidate-42/install/example-installer")]
    [InlineData("/downloads/g/candidate-42/files/example-installer.exe")]
    [InlineData("/install-personalized-script.sh")]
    [InlineData("/downloads/proof/windows/example-installer.exe")]
    [InlineData("/downloads/proof/windows/current/installers/example-installer")]
    [InlineData("/downloads/proof/windows/generations/candidate-42/files/example-installer.exe")]
    [InlineData("/downloads/proof/windows/current/artifacts/example-installer/payload")]
    [InlineData("/downloads/proof/windows/generations/candidate-42/artifacts/example-installer/metadata")]
    [InlineData("/downloads/proof/windows/candidates/6.2.0/artifacts/example-installer/payload")]
    [InlineData("/downloads/proof/windows/candidates/6.2.0/metadata")]
    public async Task ReviewRequiredShortCircuitsEveryInstallerAndUpdaterOutput(string route)
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact());
        PublicReleaseTruthProjectionDto projection = ProjectAuthority(
            manifest,
            BuildAuthorityEnvelope(manifest, "review_required"));
        var context = new DefaultHttpContext();
        context.Request.Path = route;
        context.Request.Method = HttpMethods.Get;
        using var responseBody = new MemoryStream();
        context.Response.Body = responseBody;
        bool downstreamInvoked = false;
        var middleware = new PublicReleaseTruthProjectionMiddleware(_ =>
        {
            downstreamInvoked = true;
            return Task.CompletedTask;
        });

        await InvokeMiddlewareAsync(middleware, context, new StubProjection(projection));

        Assert.False(downstreamInvoked);
        Assert.Equal(StatusCodes.Status409Conflict, context.Response.StatusCode);
        Assert.NotEmpty(context.Response.Headers[
            PublicReleaseTruthProjectionMiddleware.ProjectionHeaderName].ToString());
        responseBody.Position = 0;
        using JsonDocument body = await JsonDocument.ParseAsync(responseBody);
        PublicReleaseTruthProjectionDto? embedded = body.RootElement
            .GetProperty("releaseTruth")
            .Deserialize<PublicReleaseTruthProjectionDto>();
        Assert.Equal(JsonSerializer.Serialize(projection), JsonSerializer.Serialize(embedded));
    }

    [Fact]
    public async Task ReviewRequiredAllowsWindowsProofUploadTicketCreationToReachController()
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact());
        PublicReleaseTruthProjectionDto projection = ProjectAuthority(
            manifest,
            BuildAuthorityEnvelope(manifest, "review_required"));
        var context = new DefaultHttpContext();
        context.Request.Path = "/downloads/proof/windows/upload-ticket";
        context.Request.Method = HttpMethods.Post;
        bool downstreamInvoked = false;
        var middleware = new PublicReleaseTruthProjectionMiddleware(responseContext =>
        {
            downstreamInvoked = true;
            responseContext.Response.StatusCode = StatusCodes.Status202Accepted;
            return Task.CompletedTask;
        });

        await InvokeMiddlewareAsync(middleware, context, new StubProjection(projection));

        Assert.True(downstreamInvoked);
        Assert.Equal(StatusCodes.Status202Accepted, context.Response.StatusCode);
        Assert.NotEmpty(context.Response.Headers[
            PublicReleaseTruthProjectionMiddleware.ProjectionHeaderName].ToString());
    }

    [Theory]
    [InlineData("/downloads/files/example-installer.exe")]
    [InlineData("/downloads/files/example-payload.zip")]
    [InlineData("/downloads/files/example-payload.zip.json")]
    [InlineData("/downloads/g/candidate-42/files/example-installer.exe")]
    [InlineData("/downloads/g/candidate-42/files/example-payload.zip")]
    [InlineData("/downloads/g/candidate-42/files/example-payload.zip.json")]
    [InlineData("/downloads/g/candidate-42/install/example-installer/payload")]
    [InlineData("/downloads/g/candidate-42/install/example-installer/metadata")]
    public async Task ScopeBoundReviewAllowsOnlyRawImmutableByteRoutes(string route)
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact());
        PublicReleaseTruthProjectionDto projection = ProjectAuthority(
            manifest,
            BuildAuthorityEnvelope(
                manifest,
                "review_required",
                publicByteHandoff: true));
        var context = new DefaultHttpContext();
        context.Request.Path = route;
        context.Request.Method = HttpMethods.Get;
        bool downstreamInvoked = false;
        var middleware = new PublicReleaseTruthProjectionMiddleware(responseContext =>
        {
            downstreamInvoked = true;
            responseContext.Response.StatusCode = StatusCodes.Status204NoContent;
            return Task.CompletedTask;
        });

        await InvokeMiddlewareAsync(middleware, context, new StubProjection(projection));

        Assert.True(downstreamInvoked);
        Assert.Equal(StatusCodes.Status204NoContent, context.Response.StatusCode);
        Assert.False(projection.AvailabilityClaimsAllowed);
        Assert.False(projection.StableClaimsAllowed);
        Assert.True(projection.ReviewBannerRequired);
    }

    [Theory]
    [InlineData("/downloads/get/example-installer")]
    [InlineData("/downloads/file/example-installer")]
    [InlineData("/downloads/install/example-installer/payload")]
    [InlineData("/downloads/install/example-installer/metadata")]
    [InlineData("/downloads/g/candidate-42/install/example-installer")]
    [InlineData("/downloads/g/candidate-42/install/example-installer/PAYLOAD")]
    [InlineData("/downloads/g/candidate-42/install/EXAMPLE-installer/payload")]
    [InlineData("/downloads/g/candidate-42/install/example-installer/payload/")]
    [InlineData("/downloads/proof/windows/current/installers/example-installer")]
    [InlineData("/downloads/current.json")]
    [InlineData("/downloads/files/folder/example-installer.exe")]
    [InlineData("/downloads/g/candidate-42/files/folder/example-installer.exe")]
    public async Task ScopeBoundReviewDoesNotOpenCurrentProtectedOrOffScopeRoutes(string route)
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact());
        PublicReleaseTruthProjectionDto projection = ProjectAuthority(
            manifest,
            BuildAuthorityEnvelope(
                manifest,
                "review_required",
                publicByteHandoff: true));
        var context = new DefaultHttpContext();
        context.Request.Path = route;
        context.Request.Method = HttpMethods.Get;
        bool downstreamInvoked = false;
        var middleware = new PublicReleaseTruthProjectionMiddleware(_ =>
        {
            downstreamInvoked = true;
            return Task.CompletedTask;
        });

        await InvokeMiddlewareAsync(middleware, context, new StubProjection(projection));

        if (route == "/downloads/current.json")
        {
            Assert.True(downstreamInvoked);
            return;
        }

        Assert.False(downstreamInvoked);
        Assert.Equal(StatusCodes.Status409Conflict, context.Response.StatusCode);
    }

    [Theory]
    [InlineData("POST", "")]
    [InlineData("GET", "?ticket=credential")]
    public async Task ScopeBoundReviewRawRouteDoesNotBroadenMethodOrCredentialSemantics(
        string method,
        string query)
    {
        PublicReleaseManifestDto manifest = BuildReviewManifest(BuildPublicArtifact());
        PublicReleaseTruthProjectionDto projection = ProjectAuthority(
            manifest,
            BuildAuthorityEnvelope(
                manifest,
                "review_required",
                publicByteHandoff: true));
        var context = new DefaultHttpContext();
        context.Request.Path = "/downloads/files/example-installer.exe";
        context.Request.Method = method;
        context.Request.QueryString = new QueryString(query);
        bool downstreamInvoked = false;
        var middleware = new PublicReleaseTruthProjectionMiddleware(_ =>
        {
            downstreamInvoked = true;
            return Task.CompletedTask;
        });

        await InvokeMiddlewareAsync(middleware, context, new StubProjection(projection));

        Assert.False(downstreamInvoked);
        Assert.Equal(StatusCodes.Status409Conflict, context.Response.StatusCode);
    }

    [Theory]
    [InlineData("/downloads/files/example-installer.exe")]
    [InlineData("/downloads/g/candidate-42/files/example-installer.exe")]
    [InlineData("/downloads/get/example-installer")]
    [InlineData("/downloads/g/candidate-42/install/example-installer")]
    [InlineData("/install-personalized-script.sh")]
    [InlineData("/downloads/proof/windows/current/installers/example-installer")]
    [InlineData("/downloads/proof/windows/candidates/6.2.0/payload")]
    [InlineData("/now/concierge/read_notes")]
    [InlineData("/api/v1/install-linking/continuation/update")]
    public async Task InvalidAuthorityNeverFallsThroughToAHandoff(string route)
    {
        var context = new DefaultHttpContext();
        context.Request.Path = route;
        context.Request.Method = HttpMethods.Get;
        using var responseBody = new MemoryStream();
        context.Response.Body = responseBody;
        bool downstreamInvoked = false;
        var middleware = new PublicReleaseTruthProjectionMiddleware(_ =>
        {
            downstreamInvoked = true;
            return Task.CompletedTask;
        });

        await InvokeMiddlewareAsync(middleware, context, new ThrowingProjection());

        Assert.False(downstreamInvoked);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, context.Response.StatusCode);
        Assert.False(context.Response.Headers.ContainsKey(
            PublicReleaseTruthProjectionMiddleware.ProjectionHeaderName));
        responseBody.Position = 0;
        using JsonDocument body = await JsonDocument.ParseAsync(responseBody);
        Assert.Equal("release_truth_unavailable", body.RootElement.GetProperty("status").GetString());
    }

    [Fact]
    public async Task UnknownGenerationManifestStillPreservesTheControllerNotFoundPath()
    {
        var context = new DefaultHttpContext();
        context.Request.Path = "/downloads/g/unknown-generation/releases.json";
        bool downstreamInvoked = false;
        var middleware = new PublicReleaseTruthProjectionMiddleware(responseContext =>
        {
            downstreamInvoked = true;
            responseContext.Response.StatusCode = StatusCodes.Status404NotFound;
            return Task.CompletedTask;
        });

        await InvokeMiddlewareAsync(middleware, context, new ThrowingProjection());

        Assert.True(downstreamInvoked);
        Assert.Equal(StatusCodes.Status404NotFound, context.Response.StatusCode);
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

    [Fact]
    public async Task InvalidStagedProbeFailsClosedWithoutConsultingCommittedProjection()
    {
        var context = new DefaultHttpContext();
        context.Request.Path = "/downloads/g/candidate-42/releases.json";
        context.Request.Headers[PublicReleaseTruthProjectionMiddleware.StagedProbeHeaderName] =
            "invalid-stage-probe-token";
        bool downstreamInvoked = false;
        var middleware = new PublicReleaseTruthProjectionMiddleware(_ =>
        {
            downstreamInvoked = true;
            return Task.CompletedTask;
        });

        await InvokeMiddlewareAsync(middleware, context, new ThrowingProjection());

        Assert.False(downstreamInvoked);
        Assert.Equal(StatusCodes.Status404NotFound, context.Response.StatusCode);
        Assert.Equal(
            "private, no-store, no-cache, max-age=0",
            context.Response.Headers.CacheControl.ToString());
        Assert.Equal(
            "noindex, nofollow, noarchive",
            context.Response.Headers["X-Robots-Tag"].ToString());
        Assert.Equal(
            PublicReleaseTruthProjectionMiddleware.StagedProbeHeaderName,
            context.Response.Headers.Vary.ToString());
        Assert.False(context.Response.Headers.ContainsKey(
            PublicReleaseTruthProjectionMiddleware.ProjectionHeaderName));
    }

    private static Task InvokeMiddlewareAsync(
        PublicReleaseTruthProjectionMiddleware middleware,
        HttpContext context,
        IReleaseTruthProjection releaseTruth)
    {
        string downloadsRoot = Path.Combine(
            Path.GetTempPath(),
            "release-truth-middleware-tests",
            Guid.NewGuid().ToString("N"));
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = downloadsRoot
            })
            .Build();
        var promotions = new ReleaseBundlePromotionService(
            configuration,
            NullLogger<ReleaseBundlePromotionService>.Instance,
            promotionCheckpoint: null);
        var shelfStore = new ReleaseShelfGenerationStore(configuration);
        return middleware.InvokeAsync(context, releaseTruth, promotions, shelfStore);
    }

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

    internal static AuthorityEnvelope RebindDecision(AuthorityEnvelope authority, ReadOnlyMemory<byte> decisionBytes)
    {
        string decisionSha256 = Digest(decisionBytes);
        JsonObject snapshot = JsonNode.Parse(
            Encoding.UTF8.GetString(authority.SnapshotBytes.Span))!.AsObject();
        snapshot["releaseDecisionSha256"] = decisionSha256;
        ReadOnlyMemory<byte> snapshotBytes = Encoding.UTF8.GetBytes(snapshot.ToJsonString());
        JsonObject current = JsonNode.Parse(
            Encoding.UTF8.GetString(authority.CurrentBytes.Span))!.AsObject();
        current["decisionSha256"] = decisionSha256;
        current["snapshotSha256"] = Digest(snapshotBytes);
        ReadOnlyMemory<byte> currentBytes = Encoding.UTF8.GetBytes(current.ToJsonString());
        return authority with
        {
            CurrentBytes = currentBytes,
            SnapshotBytes = snapshotBytes,
            DecisionBytes = decisionBytes
        };
    }

    internal static AuthorityEnvelope BuildAuthorityEnvelope(
        PublicReleaseManifestDto manifest,
        string releaseDecisionStatus,
        IReadOnlyDictionary<string, string>? primaryHeads = null,
        string releaseDecisionPath = PublicReleaseAuthorityEnvelopeProjection.ReleaseDecisionPath,
        ReadOnlyMemory<byte>? manifestBytesOverride = null,
        bool publicByteHandoff = false)
    {
        ReadOnlyMemory<byte> manifestBytes = manifestBytesOverride ?? Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
        {
            contractName = "Chummer.Hub.Registry.Contracts",
            version = manifest.Version,
            channel = manifest.Channel
        }));
        string manifestSha256 = Digest(manifestBytes);
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
                publicInstallRoute = string.Equals(
                    PublicReleaseTruthProjectionService.NormalizeToken(artifact.InstallAccessClass),
                    "open_public",
                    StringComparison.Ordinal)
                    ? $"/downloads/install/{artifact.Id}"
                    : artifact.Url,
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
        var fallbackHeadsByPlatform = new SortedDictionary<string, string[]>(StringComparer.Ordinal);
        foreach (string platform in availablePlatforms)
        {
            string[] fallbackHeads = artifacts
                .Where(artifact => string.Equals(artifact.platform, platform, StringComparison.Ordinal)
                    && !string.Equals(artifact.head, primaryHeadByPlatform[platform], StringComparison.Ordinal))
                .Select(static artifact => artifact.head)
                .Distinct(StringComparer.Ordinal)
                .OrderBy(static head => head, StringComparer.Ordinal)
                .ToArray();
            if (fallbackHeads.Length > 0)
            {
                fallbackHeadsByPlatform[platform] = fallbackHeads;
            }
        }

        JsonObject decision = releaseDecisionStatus == "stable_ready"
            ? BuildStableDecisionFixture(
                manifest,
                manifestSha256,
                availablePlatforms,
                primaryHeadByPlatform,
                artifacts.Length,
                downloadAccessPosture)
            : BuildPreviewDecisionFixture(
                manifest,
                manifestSha256,
                releaseDecisionStatus,
                availablePlatforms,
                primaryHeadByPlatform,
                fallbackHeadsByPlatform,
                artifacts.Length,
                downloadAccessPosture,
                publicByteHandoff);
        ReadOnlyMemory<byte> decisionBytes = Encoding.UTF8.GetBytes(decision.ToJsonString());
        string decisionSha256 = Digest(decisionBytes);
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

    private static JsonObject BuildPreviewDecisionFixture(
        PublicReleaseManifestDto manifest,
        string manifestSha256,
        string releaseDecisionStatus,
        IReadOnlyList<string> availablePlatforms,
        IReadOnlyDictionary<string, string> primaryHeadByPlatform,
        IReadOnlyDictionary<string, string[]> fallbackHeadsByPlatform,
        int artifactCount,
        string downloadAccessPosture,
        bool publicByteHandoff)
    {
        bool ready = releaseDecisionStatus == "preview_ready";
        var decision = new JsonObject
        {
            ["contractName"] = publicByteHandoff
                ? PublicReleaseAuthorityEnvelopeProjection.PreviewDecisionContractV2
                : PublicReleaseAuthorityEnvelopeProjection.PreviewDecisionContract,
            ["generatedAt"] = "2026-07-18T12:00:00Z",
            ["status"] = releaseDecisionStatus,
            ["releaseDecisionStatus"] = releaseDecisionStatus,
            ["verdict"] = ready ? "PREVIEW_READY" : "PREVIEW_RELEASE_REVIEW_REQUIRED",
            ["releaseVersion"] = manifest.Version,
            ["releaseScopeDecisionSha256"] = ReleaseScopeDecisionSha256,
            ["channel"] = PublicReleaseTruthProjectionService.NormalizeToken(manifest.Channel),
            ["platforms"] = JsonSerializer.SerializeToNode(availablePlatforms),
            ["primaryHeadByPlatform"] = JsonSerializer.SerializeToNode(primaryHeadByPlatform),
            ["fallbackHeadsByPlatform"] = JsonSerializer.SerializeToNode(fallbackHeadsByPlatform),
            ["artifactAccessClass"] = !ready && artifactCount == 0
                ? "review_required"
                : downloadAccessPosture,
            ["supportOwner"] = "release-operations",
            ["nextActions"] = JsonSerializer.SerializeToNode(new[] { "Verify live route convergence." }),
            ["registryCommit"] = RegistryCommit,
            ["manifestSha256"] = manifestSha256,
            ["authoritySnapshotSha256"] = ready ? new string('a', 64) : string.Empty,
            ["candidateDecisionStatus"] = ready ? "review_required" : string.Empty,
            ["candidateDecisionSha256"] = ready ? new string('b', 64) : string.Empty,
            ["manifestGeneratedAt"] = "2026-07-18T11:59:00Z",
            ["scorecardSha256"] = ready ? new string('c', 64) : string.Empty,
            ["convergenceSha256"] = ready ? new string('d', 64) : string.Empty,
            ["blockingFindings"] = ready
                ? new JsonArray()
                : new JsonArray(new JsonObject
                {
                    ["id"] = "preview_1",
                    ["severity"] = "release_truth",
                    ["summary"] = "Immutable release authority still requires review."
                })
        };
        if (publicByteHandoff)
        {
            PublicReleaseArtifactDto artifact = Assert.Single(manifest.Downloads);
            decision["artifactHandoff"] = JsonSerializer.SerializeToNode(new
            {
                contractName = PublicReleaseAuthorityEnvelopeProjection.PublicPreviewByteHandoffContract,
                status = "approved_public_preview_bytes",
                sourcePublicationState = "preview",
                releaseScopeDecisionSha256 = ReleaseScopeDecisionSha256,
                releaseVersion = manifest.Version,
                channel = "preview",
                artifactId = artifact.Id,
                head = PublicReleaseTruthProjectionService.NormalizeToken(artifact.Head),
                platform = PublicReleaseTruthProjectionService.ResolvePlatformId(artifact),
                rid = (artifact.Rid ?? string.Empty).Trim().ToLowerInvariant(),
                arch = PublicReleaseTruthProjectionService.NormalizeToken(artifact.Arch),
                sha256 = artifact.Sha256.Trim().ToLowerInvariant(),
                sizeBytes = artifact.SizeBytes,
                artifactAccessClass = PublicReleaseTruthProjectionService.NormalizeToken(
                    artifact.InstallAccessClass),
                signingRequirement = "preview_unsigned_allowed",
                downloadUrl = artifact.Url,
                publicInstallRoute = $"/downloads/install/{artifact.Id}"
            });
        }

        return decision;
    }

    private static JsonObject BuildStableDecisionFixture(
        PublicReleaseManifestDto manifest,
        string manifestSha256,
        IReadOnlyList<string> availablePlatforms,
        IReadOnlyDictionary<string, string> primaryHeadByPlatform,
        int artifactCount,
        string downloadAccessPosture)
    {
        string predecessorDecisionSha256 = new('d', 64);
        string predecessorSnapshotSha256 = new('e', 64);
        return new JsonObject
        {
            ["contract_name"] = PublicReleaseAuthorityEnvelopeProjection.StableDecisionContract,
            ["contract_version"] = PublicReleaseAuthorityEnvelopeProjection.StableDecisionContractVersion,
            ["product"] = "chummer",
            ["generated_at_utc"] = "2026-07-18T12:00:00Z",
            ["status"] = "pass",
            ["verdict"] = "GOLD_READY",
            ["releaseDecisionStatus"] = "stable_ready",
            ["releaseVersion"] = manifest.Version,
            ["spine_ref"] = "products/chummer/PRODUCT_SPINE.yaml",
            ["design_ref"] = "products/chummer/PRODUCT_SPINE_REDESIGN.md",
            ["live_release"] = JsonSerializer.SerializeToNode(new
            {
                version = manifest.Version,
                channel = PublicReleaseTruthProjectionService.NormalizeToken(manifest.Channel),
                status = PublicReleaseTruthProjectionService.NormalizeToken(manifest.Status),
                rollout_state = PublicReleaseTruthProjectionService.NormalizeToken(manifest.RolloutState),
                supportability_state = PublicReleaseTruthProjectionService.NormalizeToken(manifest.SupportabilityState),
                available_platforms = availablePlatforms,
                primary_head_by_platform = primaryHeadByPlatform,
                artifact_count = artifactCount,
                download_access_posture = downloadAccessPosture,
                known_issue_summary = manifest.KnownIssueSummary,
                manifest_sha256 = manifestSha256,
                registry_commit = RegistryCommit,
                release_decision_status = "stable_ready",
                release_decision_sha256 = predecessorDecisionSha256,
                status_endpoint = "https://chummer.run/status",
                release_manifest_endpoint = "https://chummer.run/downloads/releases.json"
            }),
            ["release_authority"] = JsonSerializer.SerializeToNode(new
            {
                contract = PublicReleaseAuthorityEnvelopeProjection.AuthorityContract,
                snapshot_path = "$REGISTRY_WORKSPACE/snapshots/6.2.0/evidence/SNAPSHOT.json",
                snapshot_sha256 = predecessorSnapshotSha256,
                manifest_sha256 = manifestSha256,
                registry_commit = RegistryCommit,
                release_decision_status = "stable_ready",
                release_decision_sha256 = predecessorDecisionSha256
            }),
            ["required_loops"] = JsonSerializer.SerializeToNode(new[]
            {
                "build_correctly", "run_reliably", "remember_campaign", "explain_everything", "publish_projections"
            }),
            ["required_surfaces"] = JsonSerializer.SerializeToNode(new[]
            {
                "runner_workbench", "gm_cockpit", "campaign_memory", "living_city", "publishing_studio", "admin_proof"
            }),
            ["required_truth_domains"] = JsonSerializer.SerializeToNode(new[]
            {
                "rules_truth", "character_truth", "campaign_truth", "world_state_truth", "media_projection_truth"
            }),
            ["required_horizon_lanes"] = JsonSerializer.SerializeToNode(new[]
            {
                "alice", "karma-forge", "jackpoint", "runsite", "runbook-press", "table-pulse", "black-ledger"
            }),
            ["required_feature_lanes"] = JsonSerializer.SerializeToNode(new[]
            {
                "nexus-pan", "run-control", "edition-studio", "community-hub", "quicksilver", "ghostwire", "local-co-processor"
            }),
            ["projection_adapter_policy"] = JsonSerializer.SerializeToNode(new
            {
                status = "pass",
                adapters_are_projection_only = true,
                adapters = new[] { "rafter", "pixefy", "magicfit" }
            }),
            ["proof_inputs"] = BuildStableProofInputs(
                manifestSha256,
                predecessorSnapshotSha256,
                predecessorDecisionSha256),
            ["completion_audit"] = BuildStableCompletionAudit(),
            ["blocking_findings"] = new JsonArray(),
            ["advisory_findings"] = new JsonArray(),
            ["principle"] = "One current graph may reference many receipts, but no isolated receipt may claim whole-product gold by itself."
        };
    }

    private static JsonArray BuildStableProofInputs(
        string manifestSha256,
        string snapshotSha256,
        string decisionSha256)
    {
        const string generatedAt = "2026-07-18T11:55:00Z";
        JsonObject Base(string kind) => new()
        {
            ["kind"] = kind,
            ["path"] = $"proofs/{kind}.json",
            ["status"] = "pass"
        };
        JsonObject Receipt(string kind)
        {
            JsonObject row = Base(kind);
            row["generated_at"] = generatedAt;
            row["release_version"] = "6.2.0";
            row["snapshot_sha256"] = snapshotSha256;
            row["manifest_sha256"] = manifestSha256;
            row["release_decision_sha256"] = decisionSha256;
            return row;
        }

        var rows = new JsonArray();
        foreach (string kind in new[]
                 {
                     "design_spine", "horizon_registry", "feature_registry", "release_policy",
                     "rule_authority_human_boundaries"
                 })
        {
            rows.Add(Base(kind));
        }

        JsonObject parity = Base("parity_registry");
        parity["family_count"] = 11;
        rows.Add(parity);
        JsonObject campaign = Receipt("campaign_operability_scorecard");
        campaign["cell_count"] = 36;
        rows.Add(campaign);
        JsonObject journey = Base("journey_gates");
        journey["generated_at"] = generatedAt;
        rows.Add(journey);
        foreach (string kind in new[]
                 {
                     "fleet_flagship_readiness", "operator_release_dashboard", "final_gold_janitor",
                     "flagship_product_readiness_gate", "google_oauth_linking_proof",
                     "public_edge_postdeploy_gate", "black_ledger_live_media_proof",
                     "ui_localization_release_gate"
                 })
        {
            rows.Add(Receipt(kind));
        }

        JsonObject releaseReady = Receipt("release_ready_matrix");
        releaseReady["required_gate_count"] = 41;
        releaseReady["completed_gate_count"] = 41;
        rows.Add(releaseReady);
        JsonObject ea = Base("ea_release_critical_readiness");
        ea["generated_at"] = generatedAt;
        ea["required_component_keys"] = JsonSerializer.SerializeToNode(new[]
        {
            "google_workspace_oauth", "mymedia_alexa", "proactive_artifacts", "telegram"
        });
        ea["optional_blocked_component_keys"] = new JsonArray();
        rows.Add(ea);
        JsonObject registryAuthority = Base("registry_release_authority");
        registryAuthority["snapshot_sha256"] = snapshotSha256;
        registryAuthority["manifest_sha256"] = manifestSha256;
        registryAuthority["registry_commit"] = RegistryCommit;
        registryAuthority["release_decision_status"] = "stable_ready";
        registryAuthority["release_decision_sha256"] = decisionSha256;
        rows.Add(registryAuthority);
        rows.Add(Base("registry_stable_posture"));
        rows.Add(Base("live_status"));
        JsonObject liveManifest = Base("live_release_manifest");
        liveManifest["generated_at"] = generatedAt;
        rows.Add(liveManifest);
        return rows;
    }

    private static JsonObject BuildStableCompletionAudit()
    {
        var requirements = new JsonArray();
        void Add(string id, params string[] proofKinds) => requirements.Add(new JsonObject
        {
            ["id"] = id,
            ["status"] = "pass",
            ["proof_kinds"] = JsonSerializer.SerializeToNode(proofKinds),
            ["missing_or_failed_proof_kinds"] = new JsonArray()
        });
        Add("authoritative_design", "design_spine", "horizon_registry", "feature_registry", "release_policy");
        Add("release_control", "registry_release_authority", "registry_stable_posture", "release_ready_matrix", "final_gold_janitor", "flagship_product_readiness_gate");
        Add("journey_truth", "journey_gates", "campaign_operability_scorecard");
        Add("legacy_and_adjacent_parity", "parity_registry", "fleet_flagship_readiness");
        Add("security_and_privacy", "release_ready_matrix", "google_oauth_linking_proof", "ea_release_critical_readiness");
        Add("localization", "ui_localization_release_gate");
        Add("campaign_operability", "campaign_operability_scorecard");
        Add("installer_and_update", "release_ready_matrix", "registry_release_authority", "registry_stable_posture", "live_release_manifest");
        Add("support_and_closure", "campaign_operability_scorecard", "operator_release_dashboard", "live_status");
        Add("provider_posture", "ea_release_critical_readiness", "black_ledger_live_media_proof");
        Add("ui_quality_and_accessibility", "campaign_operability_scorecard", "public_edge_postdeploy_gate", "ui_localization_release_gate");
        Add("live_runtime", "public_edge_postdeploy_gate", "live_status", "live_release_manifest");
        return new JsonObject
        {
            ["status"] = "pass",
            ["requirement_count"] = 12,
            ["passed_count"] = 12,
            ["failed_count"] = 0,
            ["requirements"] = requirements
        };
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

    private static PublicReleaseManifestDto BuildReviewManifest(
        params PublicReleaseArtifactDto[] artifacts)
        => BuildManifest(artifacts) with
        {
            Channel = "preview",
            Status = "published",
            RolloutState = "public_release_review_required",
            SupportabilityState = "review_required"
        };

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
            Url: installAccessClass == "open_public"
                ? $"/downloads/g/candidate-42/files/{id}.exe"
                : $"/downloads/get/{id}",
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

    internal sealed record AuthorityEnvelope(
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

    private sealed class UnavailableInstallLinkingReadinessProbe
        : IInstallLinkingStoreReadinessProbe
    {
        public InstallLinkingStoreReadiness Evaluate()
            => new(false, "store_unready");
    }

    private sealed class ThrowingProjection : IReleaseTruthProjection
    {
        private static InvalidDataException Invalid()
            => new("Synthetic invalid authority envelope.");

        public PublicReleaseTruthCapture CaptureWithAuthority() => throw Invalid();

        public PublicReleaseTruthCapture CaptureGenerationWithAuthority(string generationId) => throw Invalid();

        public PublicReleaseTruthProjectionDto Capture() => throw Invalid();

        public PublicReleaseTruthProjectionDto CaptureGeneration(string generationId) => throw Invalid();

        public PublicReleaseTruthProjectionDto Project(
            PublicReleaseManifestDto manifest,
            string? immutableManifestSha256,
            ReadOnlyMemory<byte>? immutableAuthorityManifestBytes)
            => throw Invalid();
    }
}
