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
    public void AccountViewPublishesCalmAccountRailAndRecoveryFallbackCopy()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("account-rail-snapshot", view, StringComparison.Ordinal);
        Assert.Contains("Build follow-through", view, StringComparison.Ordinal);
        Assert.Contains("Recovery codes stay in reserve.", view, StringComparison.Ordinal);
        Assert.Contains("Do not turn this into a browser-first claim ritual.", view, StringComparison.Ordinal);
    }
}
