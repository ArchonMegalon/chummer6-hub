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
        Assert.Contains("Home summary", view, StringComparison.Ordinal);
        Assert.Contains("Recent change", view, StringComparison.Ordinal);
        Assert.Contains("Use as guest or link this copy later.", view, StringComparison.Ordinal);
        Assert.Contains("Keep the whole product in view, not just the current install.", view, StringComparison.Ordinal);
        Assert.Contains("Workspace", view, StringComparison.Ordinal);
        Assert.Contains("Build, explain, and next step", view, StringComparison.Ordinal);
    }

    [Fact]
    public void HomeViewFailsClosedOnRawWorkspaceDecisionNoticeNoise()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("BuildCalmHomeDecisionNoticeSummary", view, StringComparison.Ordinal);
        Assert.Contains("WorkspaceNoticeSafety.LooksLikeInternalWorkspaceLeak", view, StringComparison.Ordinal);
        Assert.Contains("leadPortableExchangeSummary", view, StringComparison.Ordinal);
        Assert.Contains("A previous campaign workspace needs attention before you continue. Open the campaign workspace for the safe next step.", view, StringComparison.Ordinal);
        Assert.Contains("Workspace note: @PublicText(leadWorkspaceDecisionNoticeSummary)", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Notice: @leadWorkspaceServerPlane.DecisionNotices[0].Summary", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Portable exchange: @leadPortableExchangeNotice.Summary", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountViewPublishesCalmAccountRailAndRecoveryFallbackCopy()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("account-rail-snapshot", view, StringComparison.Ordinal);
        Assert.Contains("Build next step", view, StringComparison.Ordinal);
        Assert.Contains("Contribution credit follows useful closeout and continuity.", view, StringComparison.Ordinal);
        Assert.Contains("Recovery codes stay in reserve.", view, StringComparison.Ordinal);
        Assert.Contains("Keep the browser step secondary.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountViewFailsClosedOnRawWorkspaceDecisionNoticeNoise()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("WorkspaceNoticeSafety.LooksLikeInternalWorkspaceLeak", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceDecisionNotices", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspacePortableExchangeSummary", view, StringComparison.Ordinal);
        Assert.Contains("A previous campaign workspace needs attention before you continue. Open the workspace sections below for the next safe step.", view, StringComparison.Ordinal);
        Assert.DoesNotContain("foreach (var notice in selectedWorkspaceServerPlane.DecisionNotices)", view, StringComparison.Ordinal);
        Assert.DoesNotContain("@selectedWorkspacePortableExchangeNotice.Summary", view, StringComparison.Ordinal);
    }
}
