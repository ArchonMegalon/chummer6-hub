using System.IO;
using Chummer.Run.Api.Services.Community;
using Microsoft.Extensions.Configuration;
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
        Assert.Contains("Turn 1 already ran. The city is moving.", landingView, System.StringComparison.Ordinal);
        Assert.Contains("Scope: \"Public aggregate\"", service, System.StringComparison.Ordinal);
        Assert.Contains("PrivacyNote:", service, System.StringComparison.Ordinal);
        Assert.Contains("ListPublicStats(int? requestedTurn = null)", service, System.StringComparison.Ordinal);
    }

    [Fact]
    public void LedgerHubRoutesAndAliasesExist()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string ledgerController = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "LedgerController.cs"));
        string ledgerView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Ledger.cshtml"));
        string landingView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Landing.cshtml"));

        Assert.Contains("[HttpGet(\"/ledger\")]", controller, System.StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/black-ledger\")]", controller, System.StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ledger/dispatches\")]", controller, System.StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ledger/dispatches/{dispatchId}\")]", controller, System.StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/karma-forge\")]", controller, System.StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"worlds/{worldId}\")]", ledgerController, System.StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"worlds/{worldId}/ticks\")]", ledgerController, System.StringComparison.Ordinal);
        Assert.Contains("Opt-in aggregate only", ledgerView, System.StringComparison.Ordinal);
        Assert.Contains("This page explains pressure, not people.", ledgerView, System.StringComparison.Ordinal);
        Assert.Contains("Stewardship transfer preview", ledgerView, System.StringComparison.Ordinal);
        Assert.Contains("Latest dispatches", ledgerView, System.StringComparison.Ordinal);
        Assert.Contains("Latest dispatch", landingView, System.StringComparison.Ordinal);
        Assert.Contains("Open Black Ledger", landingView, System.StringComparison.Ordinal);
    }

    [Fact]
    public void SeedBackedStatsLoadCurrentTurnAndPreviewProvenance()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_SEED_PATH"] = Path.GetFullPath(Path.Combine(
                    "/docker/chummercomplete",
                    "chummer-hub-registry",
                    "black-ledger",
                    "worlds",
                    "emerald-sprawl-prelude.yaml")),
            })
            .Build();

        var service = new BlackLedgerPublicStatsService(configuration);
        var stats = service.ListPublicStats();

        Assert.Contains(stats, static stat =>
            string.Equals(stat.Id, "mysad-density", System.StringComparison.Ordinal)
            && string.Equals(stat.Value, "Ashline Circle 39%", System.StringComparison.Ordinal)
            && string.Equals(stat.Period, "Turn 1", System.StringComparison.Ordinal)
            && string.Equals(stat.Source, "seeded_preview", System.StringComparison.Ordinal)
            && string.Equals(stat.ScopeKey, "public_aggregate", System.StringComparison.Ordinal)
            && string.Equals(stat.SourceDetail.Kind, "seeded_preview", System.StringComparison.Ordinal)
            && stat.SampleCount == 6);
        Assert.Contains(stats, static stat =>
            string.Equals(stat.Id, "debt-heat", System.StringComparison.Ordinal)
            && string.Equals(stat.Value, "Rust Bazaar 99 heat", System.StringComparison.Ordinal));
        Assert.Contains(stats, static stat =>
            string.Equals(stat.Id, "package-pressure", System.StringComparison.Ordinal)
            && string.Equals(stat.Value, "7 hot package candidates", System.StringComparison.Ordinal)
            && string.Equals(stat.Source, "package_registry", System.StringComparison.Ordinal)
            && string.Equals(stat.SourceDetail.Kind, "package_registry", System.StringComparison.Ordinal)
            && string.Equals(stat.SourceDetail.Label, "Package registry pressure lanes", System.StringComparison.Ordinal));

        var world = service.LoadWorldPreview();

        Assert.NotNull(world);
        Assert.Equal("emerald-sprawl-prelude", world!.WorldId);
        Assert.Equal(1, world.CurrentTurn);
        Assert.False(world.DeterministicPreview);
        Assert.Equal(8, world.Districts.Count);
        Assert.Equal(6, world.Factions.Count);
        Assert.Equal(5, world.StewardshipPosts.Count);
        Assert.NotNull(world.StewardshipTransferPreview);
        Assert.NotNull(world.LastTick);
        Assert.Equal("ledger_tick_0001_preseeded", world.LastTick!.ReceiptId);
        Assert.Equal("preseeded", world.LastTick.Mode);
        Assert.True(world.LastTick.PrivacyPassed);
    }

    [Fact]
    public void SeedBackedWorldSupportsDeterministicTurnTwoPreview()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_SEED_PATH"] = Path.GetFullPath(Path.Combine(
                    "/docker/chummercomplete",
                    "chummer-hub-registry",
                    "black-ledger",
                    "worlds",
                    "emerald-sprawl-prelude.yaml")),
            })
            .Build();

        var service = new BlackLedgerPublicStatsService(configuration);
        var world = service.LoadWorldPreview(2);
        var stats = service.ListPublicStats(2);

        Assert.NotNull(world);
        Assert.True(world!.DeterministicPreview);
        Assert.Equal(2, world.CurrentTurn);
        Assert.Contains("Turn 2 deterministic preview is ready", world.TurnHeadline, System.StringComparison.Ordinal);
        Assert.Equal("ledger_tick_0002_deterministic", world.LastTick!.ReceiptId);
        Assert.Equal("deterministic_test", world.LastTick.Mode);
        Assert.Equal(2, Assert.Single(world.TurnNavigation, static item => item.Current).Turn);
        Assert.Contains(stats, static stat =>
            string.Equals(stat.Id, "package-pressure", System.StringComparison.Ordinal)
            && string.Equals(stat.Value, "8 hot package candidates", System.StringComparison.Ordinal));
    }

    [Fact]
    public void SeedBackedWorldGeneratesReceiptBackedDispatches()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_SEED_PATH"] = Path.GetFullPath(Path.Combine(
                    "/docker/chummercomplete",
                    "chummer-hub-registry",
                    "black-ledger",
                    "worlds",
                    "emerald-sprawl-prelude.yaml")),
            })
            .Build();

        var service = new BlackLedgerPublicStatsService(configuration);
        var dispatches = service.ListDispatches();
        var latest = Assert.Single(dispatches, static item =>
            string.Equals(item.DispatchId, "ledger_dispatch_emerald-sprawl-prelude_turn_0001", System.StringComparison.Ordinal));

        Assert.Equal("ledger_tick_0001_preseeded", latest.SourceReceiptId);
        Assert.Equal("/ledger/closeouts", latest.SourceReceiptHref);
        Assert.True(latest.PublicSafe);
        Assert.True(latest.AiGenerated);
        Assert.Contains("public-safe seeded preview", latest.Body, System.StringComparison.Ordinal);
        Assert.Contains(dispatches, static item =>
            string.Equals(item.DispatchId, "ledger_dispatch_emerald-sprawl-prelude_turn_0001_rust_bazaar", System.StringComparison.Ordinal)
            && item.InvolvedDistricts.Any(static district => string.Equals(district, "Rust Bazaar", System.StringComparison.Ordinal)));
        Assert.Contains(dispatches, static item =>
            string.Equals(item.DispatchId, "ledger_dispatch_emerald-sprawl-prelude_turn_0001_ghostline", System.StringComparison.Ordinal));
    }

    [Fact]
    public void SeedBackedStatsFailClosedWhenWorldSafetyFlagsAreBroken()
    {
        string tempFile = Path.Combine(Path.GetTempPath(), $"black-ledger-unsafe-{Guid.NewGuid():N}.yaml");

        try
        {
            File.WriteAllText(tempFile, """
schema_version: 1
world_id: emerald-sprawl-prelude
public_name: Emerald Sprawl
status: preseeded_preview
source: chummer-owned seed
public_safety:
  official_lore: false
  uses_sourcebook_text: false
  uses_private_user_data: true
  public_stats_scope: opt_in_aggregate_or_seeded_fictional_preview
  real_user_identification_allowed: false
  min_sample_size_for_live_public_stats: 10
map:
  districts:
    - id: one
      name: One
      influence: 1
      heat: 1
    - id: two
      name: Two
      influence: 1
      heat: 1
    - id: three
      name: Three
      influence: 1
      heat: 1
    - id: four
      name: Four
      influence: 1
      heat: 1
    - id: five
      name: Five
      influence: 1
      heat: 1
    - id: six
      name: Six
      influence: 1
      heat: 1
    - id: seven
      name: Seven
      influence: 1
      heat: 1
    - id: eight
      name: Eight
      influence: 1
      heat: 1
factions:
  - id: ashline_circle
    public_name: Ashline Circle
    management_posts:
      faction_leader: ai_one
      field_gm: ai_two
      intel_provider: ai_three
    stats:
      mysad_density: 34
  - id: rust_market_syndicate
    public_name: Rust Market Syndicate
    management_posts:
      faction_leader: ai_one
      field_gm: ai_two
      intel_provider: ai_three
    stats:
      debt_heat: 91
  - id: f3
    public_name: F3
    management_posts:
      faction_leader: ai_one
      field_gm: ai_two
      intel_provider: ai_three
    stats: {}
  - id: f4
    public_name: F4
    management_posts:
      faction_leader: ai_one
      field_gm: ai_two
      intel_provider: ai_three
    stats: {}
  - id: f5
    public_name: F5
    management_posts:
      faction_leader: ai_one
      field_gm: ai_two
      intel_provider: ai_three
    stats: {}
  - id: f6
    public_name: F6
    management_posts:
      faction_leader: ai_one
      field_gm: ai_two
      intel_provider: ai_three
    stats: {}
ai_personalities:
  - id: ai_one
    role: faction_leader
  - id: ai_two
    role: field_gm
  - id: ai_three
    role: intel_provider
turns:
  - turn: 1
    state: preseeded_tick_complete
    summary: unsafe
    receipt_id: ledger_tick_0001_preseeded
    effects: []
    package_pressure: []
""");

            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_BLACK_LEDGER_SEED_PATH"] = tempFile,
                })
                .Build();

            var service = new BlackLedgerPublicStatsService(configuration);
            var stats = service.ListPublicStats();

            Assert.DoesNotContain(stats, static stat =>
                string.Equals(stat.Value, "Ashline Circle 34%", System.StringComparison.Ordinal));
        }
        finally
        {
            if (File.Exists(tempFile))
            {
                File.Delete(tempFile);
            }
        }
    }
}
