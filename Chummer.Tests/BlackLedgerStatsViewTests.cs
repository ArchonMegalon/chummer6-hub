using System.IO;
using Xunit;

namespace Chummer.Tests;

public sealed class BlackLedgerStatsViewTests
{
    [Fact]
    public void LandingUsesGovernedBlackLedgerStatsModel()
    {
        string landingView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Landing.cshtml"));
        string service = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Services", "Community", "BlackLedgerPublicStatsService.cs"));

        Assert.Contains("Model.BlackLedgerStats", landingView, System.StringComparison.Ordinal);
        Assert.DoesNotContain("Barrens adepts 34%", landingView, System.StringComparison.Ordinal);
        Assert.Contains("Scope: \"Public aggregate\"", service, System.StringComparison.Ordinal);
        Assert.Contains("PrivacyNote:", service, System.StringComparison.Ordinal);
        Assert.Contains("ListPublicStats()", service, System.StringComparison.Ordinal);
    }

    [Fact]
    public void LedgerHubRoutesAndAliasesExist()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string ledgerView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Ledger.cshtml"));

        Assert.Contains("[HttpGet(\"/ledger\")]", controller, System.StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/black-ledger\")]", controller, System.StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/karma-forge\")]", controller, System.StringComparison.Ordinal);
        Assert.Contains("Opt-in aggregate only", ledgerView, System.StringComparison.Ordinal);
        Assert.Contains("This page explains pressure, not people.", ledgerView, System.StringComparison.Ordinal);
    }
}
