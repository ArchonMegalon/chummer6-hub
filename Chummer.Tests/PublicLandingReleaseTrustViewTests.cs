using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingReleaseTrustViewTests
{
    [Fact]
    public void DownloadsViewKeepsCurrentReleaseKnownIssuesAndInstallHelpVisibleBesidePrimaryCta()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Open current release", view, StringComparison.Ordinal);
        Assert.Contains("@release.KnownIssuesLabel", view, StringComparison.Ordinal);
        Assert.Contains("@release.InstallHelpLabel", view, StringComparison.Ordinal);
        Assert.Contains("Known issues and install help stay nearby. Deeper release evidence lives on the current-release and status surfaces, not in front of the install button.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void DownloadsViewKeepsMainPlatformShelfVisibleBeforeAdvancedAccordion()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml");
        string view = File.ReadAllText(viewPath);

        int platformShelfIndex = view.IndexOf("id=\"platform-shelf\"", StringComparison.Ordinal);
        int advancedAccordionIndex = view.IndexOf("id=\"advanced-downloads\"", StringComparison.Ordinal);

        Assert.Contains("Main platform downloads", view, StringComparison.Ordinal);
        Assert.Contains("Windows verification and support rail", view, StringComparison.Ordinal);
        Assert.True(platformShelfIndex >= 0, "platform shelf should stay visible on the main downloads page");
        Assert.True(advancedAccordionIndex >= 0, "advanced accordion should still exist for manual and support-directed downloads");
        Assert.True(platformShelfIndex < advancedAccordionIndex, "platform shelf should appear before the advanced accordion");
    }

    [Fact]
    public void DownloadDispatchFallbackKeepsReleaseProofAndRecoveryTrustOnSameRail()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("href=\"/now\">What works today</a>", view, StringComparison.Ordinal);
        Assert.Contains("@Model.HelpLabel", view, StringComparison.Ordinal);
        Assert.Contains("Status, known issues, and install help stay on one release rail so recovery never depends on stale page copy.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void ParticipatePagePromotesCodexAuthorizationThroughOpenAiAccountFlow()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml");
        string consoleViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "CodexParticipation", "Console.cshtml");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "CodexParticipationController.cs");

        string view = File.ReadAllText(viewPath);
        string consoleView = File.ReadAllText(consoleViewPath);
        string controller = File.ReadAllText(controllerPath);

        Assert.Contains("Authorize Codex access", view, StringComparison.Ordinal);
        Assert.Contains("/auth/google/start?next=%2Fparticipate%2Fcodex", view, StringComparison.Ordinal);
        Assert.Contains("OpenAI account in ChatGPT", view, StringComparison.Ordinal);
        Assert.Contains("OpenAI account in ChatGPT", consoleView, StringComparison.Ordinal);
        Assert.Contains("authorize with your OpenAI account in ChatGPT", controller, StringComparison.Ordinal);
    }
}
