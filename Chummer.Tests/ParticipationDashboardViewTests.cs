using Xunit;

namespace Chummer.Tests;

public sealed class ParticipationDashboardViewTests
{
    [Fact]
    public void ParticipationDashboard_AccountViewPublishesDedicatedSurfaceAndSafePreferenceControls()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Participation dashboard", view, StringComparison.Ordinal);
        Assert.Contains("Contribution cred", view, StringComparison.Ordinal);
        Assert.Contains("Impact closeout notifications", view, StringComparison.Ordinal);
        Assert.Contains("publicContributionProfileOptIn", view, StringComparison.Ordinal);
        Assert.Contains("impactCloseoutNotifications", view, StringComparison.Ordinal);
        Assert.Contains("Impact journal", view, StringComparison.Ordinal);
        Assert.Contains("Votes show demand; Chummer-owned proof decides what ships.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void ParticipationDashboard_ControllerAndCanonPublishTheDedicatedParticipationRoute()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string manifestPath = RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_LANDING_MANIFEST.yaml");
        string featureRegistryPath = RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_FEATURE_REGISTRY.yaml");
        string surfaceDocPath = RepoPaths.FromRoot("docs", "PUBLIC_LANDING_SURFACE.md");

        string controller = File.ReadAllText(controllerPath);
        string manifest = File.ReadAllText(manifestPath);
        string featureRegistry = File.ReadAllText(featureRegistryPath);
        string surfaceDoc = File.ReadAllText(surfaceDocPath);

        Assert.Contains("\"participation\" => \"participation\"", controller, StringComparison.Ordinal);
        Assert.Contains("/account/participation", controller, StringComparison.Ordinal);
        Assert.Contains("/account/participation", manifest, StringComparison.Ordinal);
        Assert.Contains("purpose: signed_in_participation", manifest, StringComparison.Ordinal);
        Assert.Contains("href: /account/participation", featureRegistry, StringComparison.Ordinal);
        Assert.Contains("registered_href: /account/participation", featureRegistry, StringComparison.Ordinal);
        Assert.Contains("/account/participation", surfaceDoc, StringComparison.Ordinal);
    }

    [Fact]
    public void ParticipationConsoleAndLeaderboardsPublishCodexContributionRecognition()
    {
        string consoleViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "CodexParticipation", "Console.cshtml");
        string leaderboardViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Leaderboards", "Index.cshtml");
        string workflowCanonPath = RepoPaths.FromRoot(".codex-design", "product", "PARTICIPATION_AND_BOOSTER_WORKFLOW.md");

        string consoleView = File.ReadAllText(consoleViewPath);
        string leaderboardView = File.ReadAllText(leaderboardViewPath);
        string workflowCanon = File.ReadAllText(workflowCanonPath);

        Assert.Contains("Public Codex contribution code", consoleView, StringComparison.Ordinal);
        Assert.Contains("counts the tokens used through it", consoleView, StringComparison.Ordinal);
        Assert.Contains("Codex usage", leaderboardView, StringComparison.Ordinal);
        Assert.Contains("Codex contribution code", workflowCanon, StringComparison.Ordinal);
        Assert.Contains("participant_total_tokens", workflowCanon, StringComparison.Ordinal);
    }
}
