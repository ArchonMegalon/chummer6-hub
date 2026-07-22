using Chummer.Run.Api.Services;
using System.Text.Json;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseBundlePromotionUnsignedPreviewTests
{
    [Theory]
    [InlineData("preview", "unsigned")]
    [InlineData("preview", "skipped_preview")]
    [InlineData("PREVIEW", "UNSIGNED")]
    public void PreviewAcceptsExplicitUnsignedWindowsEvidence(string channel, string signingStatus)
    {
        Assert.True(ReleaseBundlePromotionService.IsUnsignedWindowsPreviewEvidence(channel, signingStatus));
    }

    [Theory]
    [InlineData("stable", "unsigned")]
    [InlineData("preview", "unsigned_public_release")]
    [InlineData("preview", "pass")]
    [InlineData("preview", null)]
    [InlineData(null, "unsigned")]
    public void OtherChannelAndSigningCombinationsRemainOutsidePreviewException(
        string? channel,
        string? signingStatus)
    {
        Assert.False(ReleaseBundlePromotionService.IsUnsignedWindowsPreviewEvidence(channel, signingStatus));
    }
}

public sealed class ReleaseUploadSnapshotAuthorityUnsignedCanonicalIdentityTests
{
    [Fact]
    public void ExactPreviewAliasesAreAccepted()
    {
        using JsonDocument document = JsonDocument.Parse(
            """{"version":"run-candidate","releaseVersion":"run-candidate","channel":"preview","channelId":"preview"}""");

        ReleaseUploadSnapshotAuthorityService.ValidateUnsignedManifestIdentity(
            document.RootElement,
            "run-candidate",
            "test manifest");
    }

    [Theory]
    [InlineData("{\"version\":\"run-candidate\",\"channel\":\"stable\"}")]
    [InlineData("{\"releaseVersion\":\"run-candidate\",\"channelId\":\"stable\"}")]
    [InlineData("{\"version\":\"run-candidate\"}")]
    [InlineData("{\"channel\":\"preview\"}")]
    [InlineData("{\"version\":\"wrong\",\"releaseVersion\":\"run-candidate\",\"channel\":\"preview\"}")]
    [InlineData("{\"version\":\"run-candidate\",\"channel\":\"preview\",\"channelId\":\"stable\"}")]
    public void MissingOrMismatchedAliasesAreRejected(string json)
    {
        using JsonDocument document = JsonDocument.Parse(json);

        Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadSnapshotAuthorityService.ValidateUnsignedManifestIdentity(
                document.RootElement,
                "run-candidate",
                "test manifest"));
    }

    [Fact]
    public void RetainedCanonicalArtifactMustBindExactInventoryBytes()
    {
        const string LinuxManifestSha =
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        const string LinuxInventorySha =
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
        const string WindowsSha =
            "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc";
        const string PayloadSha =
            "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd";
        using JsonDocument canonical = JsonDocument.Parse(
            $$"""
            {
              "artifacts": [
                {
                  "platform": "linux",
                  "fileName": "retained.deb",
                  "sha256": "{{LinuxManifestSha}}",
                  "sizeBytes": 10
                },
                {
                  "platform": "windows",
                  "head": "avalonia",
                  "rid": "win-x64",
                  "kind": "installer",
                  "installerMode": "bootstrap",
                  "payloadAcquisitionMode": "download",
                  "fileName": "candidate.exe",
                  "sha256": "{{WindowsSha}}",
                  "sizeBytes": 20,
                  "payloadFileName": "candidate.zip",
                  "payloadSha256": "{{PayloadSha}}",
                  "payloadSizeBytes": 30
                }
              ]
            }
            """);
        using JsonDocument fresh = JsonDocument.Parse(
            """[{"path":"files/candidate.exe"},{"path":"files/candidate.zip"}]""");
        var inventory = new Dictionary<string, ReleaseUploadCandidateInventoryRow>(
            StringComparer.Ordinal)
        {
            ["files/retained.deb"] = new("files/retained.deb", 10, LinuxInventorySha),
            ["files/candidate.exe"] = new("files/candidate.exe", 20, WindowsSha),
            ["files/candidate.zip"] = new("files/candidate.zip", 30, PayloadSha)
        };

        InvalidDataException rejected = Assert.Throws<InvalidDataException>(() =>
            ReleaseUploadSnapshotAuthorityService.ValidateUnsignedCanonicalWindows(
                canonical.RootElement,
                inventory,
                fresh.RootElement));

        Assert.Contains("canonical artifact bytes", rejected.Message, StringComparison.Ordinal);
    }
}
