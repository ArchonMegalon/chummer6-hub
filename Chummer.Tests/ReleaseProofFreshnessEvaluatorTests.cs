using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseProofFreshnessEvaluatorTests
{
    private static readonly DateTimeOffset PublishedAt = new(2026, 7, 14, 4, 11, 58, TimeSpan.Zero);

    [Fact]
    public void BareFreshTokenIsMissingRatherThanTrusted()
    {
        JsonObject proofFreshness = new() { ["status"] = "fresh" };

        ReleaseProofFreshnessEvaluation result = ReleaseProofFreshnessEvaluator.Evaluate(
            proofFreshness,
            null,
            PublishedAt,
            PublishedAt);

        Assert.False(result.IsFresh);
        Assert.Equal("missing", result.MaterializedStatus);
    }

    [Theory]
    [InlineData("releaseProofAgeSeconds")]
    [InlineData("uiLocalizationAgeSeconds")]
    [InlineData("flagshipReadinessAgeSeconds")]
    public void InconsistentEmbeddedAgeMathIsStale(string fieldName)
    {
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(PublishedAt);
        JsonObject proofFreshness = ReleaseProofEvidenceTestData.CreateFreshnessFacts(releaseProof, PublishedAt);
        proofFreshness[fieldName] = 1;

        ReleaseProofFreshnessEvaluation result = ReleaseProofFreshnessEvaluator.Evaluate(
            proofFreshness,
            releaseProof,
            PublishedAt,
            PublishedAt);

        Assert.False(result.IsFresh);
        Assert.Equal("stale", result.MaterializedStatus);
    }

    [Theory]
    [InlineData("fail", true)]
    [InlineData("passed", true)]
    [InlineData("pass", false)]
    public void FlagshipReadinessMustBePassAndDesktopReady(string status, bool desktopReady)
    {
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(PublishedAt);
        JsonObject proofFreshness = ReleaseProofEvidenceTestData.CreateFreshnessFacts(releaseProof, PublishedAt);
        proofFreshness["flagshipReadinessStatus"] = status;
        proofFreshness["flagshipDesktopClientReady"] = desktopReady;

        ReleaseProofFreshnessEvaluation result = ReleaseProofFreshnessEvaluator.Evaluate(
            proofFreshness,
            releaseProof,
            PublishedAt,
            PublishedAt);

        Assert.False(result.IsFresh);
        Assert.Equal("stale", result.MaterializedStatus);
    }

    [Fact]
    public void ExactMaxAgeIsFreshAndOneSecondBeyondIsStale()
    {
        DateTimeOffset generatedAt = PublishedAt.AddSeconds(-ReleaseProofEvidenceTestData.MaximumAgeSeconds);
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(generatedAt);
        JsonObject proofFreshness = ReleaseProofEvidenceTestData.CreateFreshnessFacts(releaseProof, PublishedAt);

        ReleaseProofFreshnessEvaluation boundary = ReleaseProofFreshnessEvaluator.Evaluate(
            proofFreshness,
            releaseProof,
            PublishedAt,
            PublishedAt);
        ReleaseProofFreshnessEvaluation expired = ReleaseProofFreshnessEvaluator.Evaluate(
            proofFreshness,
            releaseProof,
            PublishedAt,
            PublishedAt.AddSeconds(1));

        Assert.True(boundary.IsFresh);
        Assert.Equal("fresh", boundary.MaterializedStatus);
        Assert.False(expired.IsFresh);
        Assert.Equal("stale", expired.MaterializedStatus);
    }

    [Fact]
    public void ExactFutureSkewIsAcceptedAndOneSecondBeyondIsStale()
    {
        JsonObject exactProof = ReleaseProofEvidenceTestData.CreateReleaseProof(PublishedAt.AddMinutes(5));
        JsonObject beyondProof = ReleaseProofEvidenceTestData.CreateReleaseProof(PublishedAt.AddMinutes(5).AddSeconds(1));
        JsonObject exactBoundary = ReleaseProofEvidenceTestData.CreateFreshnessFacts(exactProof, PublishedAt);
        JsonObject beyondBoundary = ReleaseProofEvidenceTestData.CreateFreshnessFacts(beyondProof, PublishedAt);

        ReleaseProofFreshnessEvaluation accepted = ReleaseProofFreshnessEvaluator.Evaluate(
            exactBoundary,
            exactProof,
            PublishedAt,
            PublishedAt);
        ReleaseProofFreshnessEvaluation rejected = ReleaseProofFreshnessEvaluator.Evaluate(
            beyondBoundary,
            beyondProof,
            PublishedAt,
            PublishedAt);

        Assert.True(accepted.IsFresh);
        Assert.False(rejected.IsFresh);
        Assert.Equal("stale", rejected.MaterializedStatus);
    }

    [Fact]
    public void DeclaredMaxAgeCannotExceedSevenDayProducerPolicy()
    {
        const long sevenDaysInSeconds = 7 * 24 * 60 * 60;
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(PublishedAt);
        JsonObject exactBoundary = ReleaseProofEvidenceTestData.CreateFreshnessFacts(
            releaseProof,
            PublishedAt,
            maxAgeSeconds: sevenDaysInSeconds);
        JsonObject beyondBoundary = ReleaseProofEvidenceTestData.CreateFreshnessFacts(
            releaseProof,
            PublishedAt,
            maxAgeSeconds: sevenDaysInSeconds + 1);

        ReleaseProofFreshnessEvaluation accepted = ReleaseProofFreshnessEvaluator.Evaluate(
            exactBoundary,
            releaseProof,
            PublishedAt,
            PublishedAt);
        ReleaseProofFreshnessEvaluation rejected = ReleaseProofFreshnessEvaluator.Evaluate(
            beyondBoundary,
            releaseProof,
            PublishedAt,
            PublishedAt);

        Assert.True(accepted.IsFresh);
        Assert.False(rejected.IsFresh);
        Assert.Equal("stale", rejected.MaterializedStatus);
    }

}
