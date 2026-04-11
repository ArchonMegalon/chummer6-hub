using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingReleaseTrustViewTests
{
    [Fact]
    public void DownloadsViewKeepsCurrentReleaseProofKnownIssuesAndInstallHelpVisibleBesidePrimaryCta()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Current release proof", view, StringComparison.Ordinal);
        Assert.Contains("@release.KnownIssuesLabel", view, StringComparison.Ordinal);
        Assert.Contains("@release.InstallHelpLabel", view, StringComparison.Ordinal);
        Assert.Contains("Proof, known issues, and install help stay attached to this same release rail before you commit this machine.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void DownloadDispatchFallbackKeepsReleaseProofAndRecoveryTrustOnSameRail()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("href=\"/now\">Open current release</a>", view, StringComparison.Ordinal);
        Assert.Contains("@Model.HelpLabel", view, StringComparison.Ordinal);
        Assert.Contains("Proof, known issues, and install help stay on one release rail so recovery never depends on stale page copy.", view, StringComparison.Ordinal);
    }
}
