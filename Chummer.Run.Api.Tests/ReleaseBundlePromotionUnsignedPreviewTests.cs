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
}
