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

        Assert.Contains("Build the runner. Run the night.", landing, StringComparison.Ordinal);
        Assert.DoesNotContain("Open Black Ledger", landing, StringComparison.Ordinal);
        Assert.DoesNotContain("Replay Turn 1", landing, StringComparison.Ordinal);
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

    [Fact]
    public void BlackLedgerFaction_promo_route_exposes_cinematic_screenplay_metadata()
    {
        string publicLanding = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string promoView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "LedgerFactionPromo.cshtml"));
        string service = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Services", "Community", "BlackLedgerFactionOnboardingService.cs"));

        Assert.Contains("storyline_summary = promo.StorylineSummary", publicLanding, StringComparison.Ordinal);
        Assert.Contains("narrator_posture = promo.NarratorPosture", publicLanding, StringComparison.Ordinal);
        Assert.Contains("render_pipeline = promo.RenderPipelineLabel", publicLanding, StringComparison.Ordinal);
        Assert.Contains("screenplay_scenes = promo.ScreenplayScenes.Select", publicLanding, StringComparison.Ordinal);
        Assert.Contains("TryLoadPublicMagicFitFactionReceipt", service, StringComparison.Ordinal);
        Assert.Contains("-promo.receipt.json", service, StringComparison.Ordinal);
        Assert.Contains("How the reel is structured", promoView, StringComparison.Ordinal);
        Assert.Contains("@Model.Promo.RenderPipelineLabel", promoView, StringComparison.Ordinal);
        Assert.Contains("@foreach (var scene in Model.Promo.ScreenplayScenes)", promoView, StringComparison.Ordinal);
    }
}
