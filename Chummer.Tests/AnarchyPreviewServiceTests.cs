using Chummer.Run.Api.Services.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class AnarchyPreviewServiceTests
{
    private static IConfiguration BuildConfiguration()
        => new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_SEED_PATH"] = Path.GetFullPath(Path.Combine(RepoPaths.Root, "..", "chummer-hub-registry", "black-ledger", "worlds", "emerald-sprawl-prelude.yaml")),
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(Path.GetTempPath(), $"chummer-anarchy-preview-{Guid.NewGuid():N}.json"),
            })
            .Build();

    [Fact]
    public void AnarchyPreviewService_exposes_dedicated_ruleset_profile_and_export()
    {
        var configuration = BuildConfiguration();
        var dispatches = new BlackLedgerDispatchService(
            new CommunityStore(configuration, NullLogger<CommunityStore>.Instance),
            new BlackLedgerPublicStatsService(configuration),
            NullLogger<BlackLedgerDispatchService>.Instance);
        var service = new AnarchyPreviewService(dispatches);

        var profile = service.LoadFeaturedProfile();
        string exportJson = service.BuildExportJson();
        var explain = service.BuildExplainReceipt();

        Assert.Equal("shadowrun_anarchy", profile.RulesetId);
        Assert.Equal("Playable preview", profile.VerdictLabel);
        Assert.Contains("shadowrun_anarchy", exportJson, StringComparison.Ordinal);
        Assert.Contains("ledger_tick_0001_preseeded", exportJson, StringComparison.Ordinal);
        Assert.Equal("shadowrun_anarchy", explain.RulesetId);
        Assert.Contains(explain.ProvenanceNotes, note => note.Contains("dedicated ruleset", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AnarchyPreviewService_dispatch_lane_is_receipt_backed()
    {
        var configuration = BuildConfiguration();
        var dispatches = new BlackLedgerDispatchService(
            new CommunityStore(configuration, NullLogger<CommunityStore>.Instance),
            new BlackLedgerPublicStatsService(configuration),
            NullLogger<BlackLedgerDispatchService>.Instance);
        var service = new AnarchyPreviewService(dispatches);

        var items = service.ListDispatches();

        Assert.NotEmpty(items);
        Assert.All(items, item => Assert.Equal("ledger_tick_0001_preseeded", item.SourceReceiptId));
    }
}
