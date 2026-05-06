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
        Assert.Contains("Keep the whole route in view, not just the current install.", view, StringComparison.Ordinal);
        Assert.Contains("home-hub-and-registry", view, StringComparison.Ordinal);
        Assert.Contains("home-mobile-play-shell", view, StringComparison.Ordinal);
        Assert.Contains("home-ui-kit-and-flagship-polish", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountViewPublishesCalmAccountRailAndRecoveryFallbackCopy()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("account-rail-snapshot", view, StringComparison.Ordinal);
        Assert.Contains("Account rail", view, StringComparison.Ordinal);
        Assert.Contains("Recovery codes stay fallback only.", view, StringComparison.Ordinal);
        Assert.Contains("Do not turn this into a browser-first claim ritual.", view, StringComparison.Ordinal);
    }
}
