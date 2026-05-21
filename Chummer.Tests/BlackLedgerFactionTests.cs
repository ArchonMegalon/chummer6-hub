using System.IO;
using Xunit;

namespace Chummer.Tests;

public sealed class BlackLedgerFactionTests
{
    [Fact]
    public void BlackLedgerFaction_public_frontdoor_and_profile_routes_exist()
    {
        string landing = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Landing.cshtml"));
        string publicLanding = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string ledgerView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Ledger.cshtml"));

        Assert.Contains("The city is moving.", landing, StringComparison.Ordinal);
        Assert.Contains("Open a file, read the pressure, or replay Turn 1 without touching private table state.", landing, StringComparison.Ordinal);
        Assert.Contains("Open Black Ledger", landing, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ledger/factions\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ledger/factions/{factionId}\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("Open faction file", ledgerView, StringComparison.Ordinal);
        Assert.Contains("Private labels stay private.", File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "LedgerFactionWorkspace.cshtml")), StringComparison.Ordinal);
    }

    [Fact]
    public void BlackLedgerFaction_management_routes_exist_and_stay_authenticated()
    {
        string publicLanding = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));

        Assert.Contains("[HttpGet(\"/account/ledger/factions/{factionId}\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/ledger/factions/{factionId}/manage\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/ledger/factions/{factionId}/stewards\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/ledger/factions/{factionId}/private-lore\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("return Redirect($\"/login?next={Uri.EscapeDataString(currentPath)}\")", publicLanding, StringComparison.Ordinal);
    }
}
