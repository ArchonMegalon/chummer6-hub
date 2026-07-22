using Chummer.Run.Api.Services;

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
