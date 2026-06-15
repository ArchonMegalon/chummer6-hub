using System.IO;
using Xunit;

namespace Chummer.Tests;

public sealed class BlackLedgerNewsroomTests
{
    [Fact]
    public void BlackLedgerNewsroom_public_routes_and_watch_contract_exist()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string ledgerView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Ledger.cshtml"));
        string briefingService = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Services", "Community", "BlackLedgerWorldTickBriefingService.cs"));
        string siteViewModels = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs"));

        Assert.Contains("[HttpGet(\"/ledger/newsroom\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ledger/newsroom/{episodeId}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ledger/newsroom/{episodeId}/transcript\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ledger/newsroom/{episodeId}/receipts\")]", controller, StringComparison.Ordinal);
        Assert.Contains("TryParseNewsroomEpisodeTurn", controller, StringComparison.Ordinal);

        Assert.Contains("Black Ledger Newsroom", ledgerView, StringComparison.Ordinal);
        Assert.Contains("Open watch route", ledgerView, StringComparison.Ordinal);
        Assert.Contains("Transcript", ledgerView, StringComparison.Ordinal);
        Assert.Contains("Episode details", ledgerView, StringComparison.Ordinal);
        Assert.Contains("Feedback", ledgerView, StringComparison.Ordinal);

        Assert.Contains("TranscriptHref", siteViewModels, StringComparison.Ordinal);
        Assert.Contains("ReceiptsHref", siteViewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSafetyNote", siteViewModels, StringComparison.Ordinal);
        Assert.Contains("ReconstructionNote", siteViewModels, StringComparison.Ordinal);
        Assert.Contains("FeedbackHref", siteViewModels, StringComparison.Ordinal);

        Assert.Contains("string watchHref = $\"{ledgerBasePath.TrimEnd('/')}/newsroom/{slug}\";", briefingService, StringComparison.Ordinal);
        Assert.Contains("string transcriptHref = $\"{ledgerBasePath.TrimEnd('/')}/newsroom/{slug}/transcript\";", briefingService, StringComparison.Ordinal);
        Assert.Contains("string receiptsHref = $\"{ledgerBasePath.TrimEnd('/')}/newsroom/{slug}/receipts\";", briefingService, StringComparison.Ordinal);
        Assert.Contains("PackageLabel: $\"Turn {tick.Turn} anchor package\"", briefingService, StringComparison.Ordinal);
        Assert.Contains("City bulletin only. No private table data.", briefingService, StringComparison.Ordinal);
        Assert.Contains("Some shots restage city movement.", briefingService, StringComparison.Ordinal);
        Assert.Contains("? $\"Black Ledger newsroom · {worldTurnBriefing?.Broadcast?.PackageLabel", controller, StringComparison.Ordinal);
        Assert.Contains("Turn {newsTurn} anchor package", controller, StringComparison.Ordinal);
        Assert.Contains("? $\"Black Ledger dispatches · {worldTitle}\"", controller, StringComparison.Ordinal);
        Assert.Contains("? $\"Black Ledger packages · {worldTitle}\"", controller, StringComparison.Ordinal);
        Assert.Contains("? $\"Black Ledger closeouts · {worldTitle}\"", controller, StringComparison.Ordinal);
        Assert.Contains("? $\"Black Ledger world stats · {worldTitle}\"", controller, StringComparison.Ordinal);
        Assert.Contains("? $\"Black Ledger factions · {worldTitle}\"", controller, StringComparison.Ordinal);
    }
}
