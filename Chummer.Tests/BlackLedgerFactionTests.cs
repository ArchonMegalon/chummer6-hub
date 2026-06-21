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

        Assert.Contains("Build and maintain Shadowrun characters without losing the details between sessions.", landing, StringComparison.Ordinal);
        Assert.DoesNotContain("Open Black Ledger", landing, StringComparison.Ordinal);
        Assert.DoesNotContain("Replay Turn 1", landing, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ledger/factions\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ledger/factions/{factionId}\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("Open faction file", ledgerView, StringComparison.Ordinal);
        Assert.Contains("<a href=\"@newsreelBroadcast.ReceiptsHref\">Details</a>", ledgerView, StringComparison.Ordinal);
        Assert.Contains("<span>Turn: @selectedTurn</span>", ledgerView, StringComparison.Ordinal);
        Assert.Contains("<p>Latest turn: Turn @selectedTurn</p>", ledgerView, StringComparison.Ordinal);
        Assert.Contains("Faction pages show pressure, not private people.", ledgerView, StringComparison.Ordinal);
        Assert.DoesNotContain("Episode details", ledgerView, StringComparison.Ordinal);
        Assert.DoesNotContain("Latest turn: @ledger.SourceReceipt", ledgerView, StringComparison.Ordinal);
        Assert.DoesNotContain("world.LastTick?.ReceiptId", ledgerView, StringComparison.Ordinal);
        Assert.DoesNotContain("Package pressure visible", ledgerView, StringComparison.Ordinal);
        Assert.DoesNotContain("Public faction lanes", ledgerView, StringComparison.Ordinal);
        string workspaceView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "LedgerFactionWorkspace.cshtml"));
        Assert.Contains("Private labels stay private.", workspaceView, StringComparison.Ordinal);
        Assert.Contains("Connected workspace section", workspaceView, StringComparison.Ordinal);
        Assert.DoesNotContain("Connected command lane", workspaceView, StringComparison.Ordinal);
        Assert.DoesNotContain("Connected command path", workspaceView, StringComparison.Ordinal);
        Assert.DoesNotContain("Faction workspace lanes", workspaceView, StringComparison.Ordinal);
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
        Assert.Contains("Storyboard mode", promoView, StringComparison.Ordinal);
        Assert.Contains("Every faction video page includes video files", promoView, StringComparison.Ordinal);
        Assert.DoesNotContain("Every faction video route", promoView, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("faction-storyboard-frame__payoff", promoView, StringComparison.Ordinal);
        Assert.DoesNotContain("Fallback mode:", promoView, StringComparison.Ordinal);
        Assert.DoesNotContain("faction-storyboard-frame__proof", promoView, StringComparison.Ordinal);
        Assert.Contains("PublicFacingCopyHumanizer.Clean(Model.Promo.RenderPipelineLabel)", promoView, StringComparison.Ordinal);
        Assert.Contains("@foreach (var scene in Model.Promo.ScreenplayScenes)", promoView, StringComparison.Ordinal);
    }
}
