using Xunit;

namespace Chummer.Tests;

public sealed class SignedInShellContinuityViewTests
{
    [Fact]
    public void HomeViewPublishesContinuityCockpitAndWhatChangedPacket()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("home-cockpit-strip", view, StringComparison.Ordinal);
        Assert.Contains("Continuity cockpit", view, StringComparison.Ordinal);
        Assert.Contains("What changed for me", view, StringComparison.Ordinal);
        Assert.Contains("Use as guest or link this copy later.", view, StringComparison.Ordinal);
        Assert.Contains("Keep the whole product in view, not just the current install.", view, StringComparison.Ordinal);
        Assert.Contains("Campaign workspace", view, StringComparison.Ordinal);
        Assert.Contains("Build handoff", view, StringComparison.Ordinal);
    }

    [Fact]
    public void HomeViewFailsClosedOnRawWorkspaceDecisionNoticeNoise()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("BuildCalmHomeDecisionNoticeSummary", view, StringComparison.Ordinal);
        Assert.Contains("WorkspaceNoticeSafety.LooksLikeInternalWorkspaceLeak", view, StringComparison.Ordinal);
        Assert.Contains("leadPortableExchangeSummary", view, StringComparison.Ordinal);
        Assert.Contains("A previous campaign workspace needs review before you continue. Open the campaign workspace for the safe next step.", view, StringComparison.Ordinal);
        Assert.Contains("Workspace review: @leadWorkspaceDecisionNoticeSummary", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Notice: @leadWorkspaceServerPlane.DecisionNotices[0].Summary", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Portable exchange: @leadPortableExchangeNotice.Summary", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountViewPublishesCalmAccountRailAndRecoveryFallbackCopy()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("account-rail-snapshot", view, StringComparison.Ordinal);
        Assert.Contains("Build follow-through", view, StringComparison.Ordinal);
        Assert.Contains("Support follow-through", view, StringComparison.Ordinal);
        Assert.Contains("Recovery codes stay in reserve.", view, StringComparison.Ordinal);
        Assert.Contains("Do not turn this into a browser-first claim ritual.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountViewFailsClosedOnRawWorkspaceDecisionNoticeNoise()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("WorkspaceNoticeSafety.LooksLikeInternalWorkspaceLeak", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceDecisionNotices", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspacePortableExchangeSummary", view, StringComparison.Ordinal);
        Assert.Contains("A previous campaign workspace needs review before you continue. Open the workspace lanes below for the safe next step.", view, StringComparison.Ordinal);
        Assert.DoesNotContain("foreach (var notice in selectedWorkspaceServerPlane.DecisionNotices)", view, StringComparison.Ordinal);
        Assert.DoesNotContain("@selectedWorkspacePortableExchangeNotice.Summary", view, StringComparison.Ordinal);
    }
}
