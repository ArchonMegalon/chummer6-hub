using Chummer.Run.Api.Services.Community;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class BlackLedgerMapTests
{
    [Fact]
    public void BlackLedgerMap_service_builds_public_safe_command_map()
    {
        var service = new BlackLedgerPublicStatsService(BuildSeedConfiguration());

        var map = service.LoadCommandMap(1, "conflict");

        Assert.NotNull(map);
        Assert.Equal("conflict", map.CurrentMode);
        Assert.Equal("svg_tactical", map.RenderMode);
        Assert.NotEmpty(map.Events);
        Assert.NotEmpty(map.Arcs);
        Assert.Contains(map.Modes, item => item.Id == "recent-changes");
    }

    [Fact]
    public void BlackLedgerMap_api_document_exposes_regions_factions_events_and_replay()
    {
        var service = new BlackLedgerPublicStatsService(BuildSeedConfiguration());

        BlackLedgerMapApiDocument? map = service.LoadCommandMapDocument(1, "influence");

        Assert.NotNull(map);
        Assert.Equal("emerald-sprawl-prelude", map.WorldId);
        Assert.NotEmpty(map.Regions);
        Assert.NotEmpty(map.Factions);
        Assert.NotEmpty(map.Events);
        Assert.NotEmpty(map.ReplaySteps);
    }

    [Fact]
    public void BlackLedgerMap_tick_delta_reports_changed_regions_and_dispatch_ids()
    {
        var service = new BlackLedgerPublicStatsService(BuildSeedConfiguration());

        BlackLedgerTickDeltaApiDocument? delta = service.LoadTickDelta(0, 1);

        Assert.NotNull(delta);
        Assert.Equal(0, delta.FromTurn);
        Assert.Equal(1, delta.ToTurn);
        Assert.NotEmpty(delta.RegionDeltas);
        Assert.NotEmpty(delta.DispatchIds);
    }

    [Fact]
    public void BlackLedgerMap_route_family_exists_in_public_and_api_controllers()
    {
        string publicLanding = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string ledgerApi = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "LedgerController.cs"));

        Assert.Contains("[HttpGet(\"/ledger/map\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ledger/factions/{factionId}\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ledger/turns/{turn}\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"worlds/{worldId}/map\")]", ledgerApi, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"worlds/{worldId}/map/turns/{turn:int}\")]", ledgerApi, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"worlds/{worldId}/map/tick-delta/{fromTurn:int}/{toTurn:int}\")]", ledgerApi, StringComparison.Ordinal);
    }

    private static IConfiguration BuildSeedConfiguration()
    {
        Dictionary<string, string?> values = new(StringComparer.OrdinalIgnoreCase)
        {
            ["CHUMMER_BLACK_LEDGER_SEED_PATH"] = RepoPaths.FromRoot("..", "chummer-hub-registry", "black-ledger", "worlds", "emerald-sprawl-prelude.yaml"),
        };

        return new ConfigurationBuilder()
            .AddInMemoryCollection(values)
            .Build();
    }
}
