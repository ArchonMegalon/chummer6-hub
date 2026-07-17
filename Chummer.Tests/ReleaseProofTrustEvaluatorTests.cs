using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseProofTrustEvaluatorTests
{
    private static readonly DateTimeOffset GeneratedAt =
        new(2026, 7, 14, 4, 11, 58, TimeSpan.Zero);

    [Fact]
    public void RegistryGeneratedNonBmpUnicodeSnapshotIsAccepted()
    {
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(GeneratedAt);
        JsonObject readiness = releaseProof["flagshipReadiness"]!.AsObject();
        readiness["reason"] = "Ready 🦾";
        readiness["snapshotSha256"] =
            "sha256:69e930d6319d962cc6fe8bc4d640daab90a91fd70975522bba3979331bc291fe";

        ReleaseProofTrustEvaluation result = ReleaseProofTrustEvaluator.Validate(releaseProof);

        Assert.True(result.IsValid, result.Reason);
    }

    [Fact]
    public void RegistryPythonUnicodeSortOrderIsAcceptedForBlockers()
    {
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(
            GeneratedAt,
            readinessStatus: "fail",
            desktopClientReady: false,
            launchBlockers: ["\uE000", "🦾"]);
        releaseProof["flagshipReadiness"]!["snapshotSha256"] =
            "sha256:97b514bb4e5db38fec0c4de68dc84ca7855303d84ee602d23eb4b37be450a9cd";

        ReleaseProofTrustEvaluation result = ReleaseProofTrustEvaluator.Validate(releaseProof);

        Assert.True(result.IsValid, result.Reason);
        Assert.False(result.FlagshipReadinessPasses);
    }

    [Fact]
    public void NonCanonicalReadinessStatusIsRejectedEvenWithMatchingDigest()
    {
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(
            GeneratedAt,
            readinessStatus: "PASS");

        ReleaseProofTrustEvaluation result = ReleaseProofTrustEvaluator.Validate(releaseProof);

        Assert.False(result.IsValid);
    }

    [Fact]
    public void NonCanonicalCoverageGapKeyIsRejectedEvenWithMatchingDigest()
    {
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(
            GeneratedAt,
            readinessStatus: "fail",
            desktopClientReady: false,
            coverageGapKeys: ["Not Canonical"]);

        ReleaseProofTrustEvaluation result = ReleaseProofTrustEvaluator.Validate(releaseProof);

        Assert.False(result.IsValid);
    }

    [Fact]
    public void CoverageGapCountOverRegistryLimitIsRejectedEvenWithMatchingDigest()
    {
        string[] coverageGapKeys = Enumerable.Range(0, 129)
            .Select(static index => $"gap.{index:D3}")
            .ToArray();
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(
            GeneratedAt,
            readinessStatus: "fail",
            desktopClientReady: false,
            coverageGapKeys: coverageGapKeys);

        ReleaseProofTrustEvaluation result = ReleaseProofTrustEvaluator.Validate(releaseProof);

        Assert.False(result.IsValid);
    }

    [Theory]
    [InlineData("Contact jane@example.com before launch.")]
    [InlineData("Inspect /home/operator/private/readiness.json before launch.")]
    [InlineData(" leading whitespace is not canonical")]
    [InlineData("trailing whitespace is not canonical ")]
    public void RegistryInvalidReasonTextIsRejectedEvenWithMatchingDigest(string reason)
    {
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(GeneratedAt);
        JsonObject readiness = releaseProof["flagshipReadiness"]!.AsObject();
        readiness["reason"] = reason;
        RebindAsciiSnapshotDigest(readiness);

        ReleaseProofTrustEvaluation result = ReleaseProofTrustEvaluator.Validate(releaseProof);

        Assert.False(result.IsValid);
    }

    [Fact]
    public void ReasonOverRegistryLengthLimitIsRejectedEvenWithMatchingDigest()
    {
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(GeneratedAt);
        JsonObject readiness = releaseProof["flagshipReadiness"]!.AsObject();
        readiness["reason"] = new string('x', 4097);
        RebindAsciiSnapshotDigest(readiness);

        ReleaseProofTrustEvaluation result = ReleaseProofTrustEvaluator.Validate(releaseProof);

        Assert.False(result.IsValid);
    }

    [Theory]
    [InlineData("Contact jane@example.com before launch.")]
    [InlineData("Inspect C:\\Users\\operator\\private\\readiness.json before launch.")]
    public void RegistryInvalidBlockerTextIsRejectedEvenWithMatchingDigest(string blocker)
    {
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(
            GeneratedAt,
            readinessStatus: "fail",
            desktopClientReady: false,
            launchBlockers: [blocker]);

        ReleaseProofTrustEvaluation result = ReleaseProofTrustEvaluator.Validate(releaseProof);

        Assert.False(result.IsValid);
    }

    [Fact]
    public void BlockerOverRegistryLengthLimitIsRejectedEvenWithMatchingDigest()
    {
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(
            GeneratedAt,
            readinessStatus: "fail",
            desktopClientReady: false,
            launchBlockers: [new string('x', 1025)]);

        ReleaseProofTrustEvaluation result = ReleaseProofTrustEvaluator.Validate(releaseProof);

        Assert.False(result.IsValid);
    }

    [Fact]
    public void BlockerCountOverRegistryLimitIsRejectedEvenWithMatchingDigest()
    {
        string[] launchBlockers = Enumerable.Range(0, 129)
            .Select(static index => $"Blocker {index:D3}")
            .ToArray();
        JsonObject releaseProof = ReleaseProofEvidenceTestData.CreateReleaseProof(
            GeneratedAt,
            readinessStatus: "fail",
            desktopClientReady: false,
            launchBlockers: launchBlockers);

        ReleaseProofTrustEvaluation result = ReleaseProofTrustEvaluator.Validate(releaseProof);

        Assert.False(result.IsValid);
    }

    private static void RebindAsciiSnapshotDigest(JsonObject readiness)
    {
        JsonObject digestMaterial = new()
        {
            ["contractName"] = readiness["contractName"]?.DeepClone(),
            ["coverageGapKeys"] = readiness["coverageGapKeys"]?.DeepClone(),
            ["desktopClientReady"] = readiness["desktopClientReady"]?.DeepClone(),
            ["generatedAt"] = readiness["generatedAt"]?.DeepClone(),
            ["launchBlockers"] = readiness["launchBlockers"]?.DeepClone(),
            ["reason"] = readiness["reason"]?.DeepClone(),
            ["sourceSha256"] = readiness["sourceSha256"]?.DeepClone(),
            ["status"] = readiness["status"]?.DeepClone()
        };
        string canonical = digestMaterial.ToJsonString(new JsonSerializerOptions
        {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            WriteIndented = false
        });
        readiness["snapshotSha256"] = "sha256:" + Convert.ToHexString(
            SHA256.HashData(Encoding.UTF8.GetBytes(canonical))).ToLowerInvariant();
    }
}
