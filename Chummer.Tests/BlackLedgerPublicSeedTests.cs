using System.IO;
using Chummer.Run.Api.Services.Community;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class BlackLedgerPublicSeedTests
{
    [Fact]
    public void BlackLedgerPublicSeed_registry_seed_uses_public_safe_schema_and_counts()
    {
        var service = new BlackLedgerPublicStatsService(BuildSeedConfiguration());
        var seed = service.LoadSeedDocument();

        Assert.NotNull(seed);
        Assert.Equal("emerald-sprawl-prelude", seed!.WorldId);
        Assert.Equal("public_seed", seed.LoreMode);
        Assert.False(seed.OfficialIpNamesPresent);
        Assert.False(seed.SourcebookTextPresent);
        Assert.Equal(6, seed.Factions!.Count);
        Assert.Equal(8, seed.Districts!.Count);
    }

    [Fact]
    public void BlackLedgerPublicSeed_public_routes_exist_in_controller_sources()
    {
        string ledgerApi = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "LedgerController.cs"));
        string landing = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Landing.cshtml"));

        Assert.Contains("[HttpGet(\"worlds/{worldId}\")]", ledgerApi, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"worlds/{worldId}/turns/{turn:int}\")]", ledgerApi, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"worlds/{worldId}/dispatches\")]", ledgerApi, StringComparison.Ordinal);
        Assert.Contains("Turn 1 already ran. The city is moving.", landing, StringComparison.Ordinal);
        Assert.Contains("Replay Turn 1", landing, StringComparison.Ordinal);
    }

    private static IConfiguration BuildSeedConfiguration()
        => new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_SEED_PATH"] = RepoPaths.FromRoot("..", "chummer-hub-registry", "black-ledger", "worlds", "emerald-sprawl-prelude.yaml"),
            })
            .Build();
}
