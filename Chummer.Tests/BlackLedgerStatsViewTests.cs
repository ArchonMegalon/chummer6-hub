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
        Assert.Contains("The city is moving.", landingView, System.StringComparison.Ordinal);
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
        string service = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Services", "Community", "BlackLedgerPublicStatsService.cs"));
        Assert.Contains("pressure, not people", ledgerView, System.StringComparison.Ordinal);
        Assert.Contains("Closeout Feed", service, System.StringComparison.Ordinal);
        Assert.Contains("Replay Turn 1", landingView, System.StringComparison.Ordinal);
        Assert.Contains("carry your runners into the Black Ledger", landingView, System.StringComparison.Ordinal);
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
            && string.Equals(stat.Value, "Ashline Circle 34%", System.StringComparison.Ordinal)
            && string.Equals(stat.Period, "Turn 2", System.StringComparison.Ordinal)
            && string.Equals(stat.Source, "seeded_board", System.StringComparison.Ordinal)
            && string.Equals(stat.ScopeKey, "public_aggregate", System.StringComparison.Ordinal)
            && string.Equals(stat.SourceDetail.Kind, "seeded_board", System.StringComparison.Ordinal)
            && stat.SampleCount == 6);
        Assert.Contains(stats, static stat =>
            string.Equals(stat.Id, "debt-heat", System.StringComparison.Ordinal)
            && string.Equals(stat.Value, "Rust Bazaar 91 heat", System.StringComparison.Ordinal));
        Assert.Contains(stats, static stat =>
            string.Equals(stat.Id, "package-pressure", System.StringComparison.Ordinal)
            && string.Equals(stat.Value, "7 hot package candidates", System.StringComparison.Ordinal)
            && string.Equals(stat.Source, "package_registry", System.StringComparison.Ordinal)
            && string.Equals(stat.SourceDetail.Kind, "package_registry", System.StringComparison.Ordinal)
            && string.Equals(stat.SourceDetail.Label, "Package registry pressure lanes", System.StringComparison.Ordinal));

        var world = service.LoadWorldPreview();

        Assert.NotNull(world);
        Assert.Equal("emerald-sprawl-prelude", world!.WorldId);
        Assert.Equal(2, world.CurrentTurn);
        Assert.False(world.DeterministicPreview);
        Assert.Equal(8, world.Districts.Count);
        Assert.Equal(6, world.Factions.Count);
        Assert.Equal(4, world.StewardshipPosts.Count);
        Assert.NotNull(world.LastTick);
        Assert.Equal("ledger_tick_0002_flagship_seeded", world.LastTick!.ReceiptId);
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
        Assert.Contains("Turn 2", world.TurnHeadline, System.StringComparison.Ordinal);
        Assert.Equal("ledger_tick_0002_flagship_seeded", world.LastTick!.ReceiptId);
        Assert.Equal("preseeded", world.LastTick.Mode);
        Assert.Contains(world.TurnNavigation, static item => item.Turn == 2 && item.Current);
        Assert.Contains(stats, static stat =>
            string.Equals(stat.Id, "package-pressure", System.StringComparison.Ordinal)
            && string.Equals(stat.Value, "7 hot package candidates", System.StringComparison.Ordinal));
        Assert.Equal("flagship_seeded", service.LoadSeedDocument()!.Status);
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
            string.Equals(item.DispatchId, "dispatch_turn_0001_main", System.StringComparison.Ordinal));

        Assert.Equal("ledger_tick_0001_preseeded", latest.SourceReceiptId);
        Assert.Equal("/ledger/turns/1", latest.SourceReceiptHref);
        Assert.True(latest.PublicSafe);
        Assert.True(latest.AiGenerated);
        Assert.Contains("Seeded preview, public-safe aggregate only.", latest.Body, System.StringComparison.Ordinal);
        Assert.Contains(dispatches, static item =>
            string.Equals(item.DispatchId, "dispatch_turn_0001_rust_market_old_favors", System.StringComparison.Ordinal)
            && item.InvolvedDistricts.Any(static district => string.Equals(district, "Rust Bazaar", System.StringComparison.Ordinal)));
        Assert.Contains(dispatches, static item =>
            string.Equals(item.DispatchId, "dispatch_turn_0001_ghostline_rumor_suppressed", System.StringComparison.Ordinal));
    }

    [Fact]
    public void SeedBackedWorldBuildsProfessionalTurnAndLeaderBriefings()
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

        var stats = new BlackLedgerPublicStatsService(configuration);
        var factions = BlackLedgerFactionAllegianceTests.CreateService();
        var service = new BlackLedgerWorldTickBriefingService(stats, factions);

        var briefing = service.BuildWorldTurnBriefing(1);
        var digest = service.BuildLeaderDigest("ashline-circle", 1);
        var packet = service.BuildValidationPacket(1, "ashline-circle");

        Assert.NotNull(briefing);
        Assert.Equal(0, briefing!.FromTurn);
        Assert.Equal(1, briefing.ToTurn);
        Assert.Contains("Turn 0", briefing.TransitionNarrative, System.StringComparison.Ordinal);
        Assert.Contains("newsreel.json", briefing.ValidationJsonHref, System.StringComparison.Ordinal);
        Assert.NotNull(briefing.Broadcast);
        Assert.Contains("/media/ledger/newsreels/turn-1-newsreel.mp4", briefing.Broadcast!.VideoMp4Href, System.StringComparison.Ordinal);
        Assert.Contains(".vtt", briefing.Broadcast.CaptionsHref, System.StringComparison.Ordinal);
        Assert.True(briefing.Broadcast.ActionBeats.Count >= 5);
        Assert.Contains(briefing.Broadcast.ActionBeats, beat => string.Equals(beat.ActorKind, "player", System.StringComparison.OrdinalIgnoreCase));
        Assert.Contains(briefing.Broadcast.ActionBeats, beat => string.Equals(beat.ActorKind, "gm", System.StringComparison.OrdinalIgnoreCase));
        Assert.NotNull(digest);
        Assert.Equal("ashline-circle", digest!.FactionId);
        Assert.NotEmpty(digest.PressureCalls);
        Assert.NotEmpty(digest.RecommendedActions);
        Assert.NotNull(packet);
        Assert.Contains("/account/ledger/factions/ashline-circle/leader-briefing", packet!.Links, System.StringComparer.Ordinal);

        var deterministicBriefing = service.BuildWorldTurnBriefing(2);
        Assert.NotNull(deterministicBriefing);
        Assert.Equal(2, deterministicBriefing!.ToTurn);
        Assert.Equal("/ledger/turns/2#newsreel-player", deterministicBriefing.Broadcast!.WatchHref);
        Assert.Contains("/media/ledger/newsreels/turn-2-newsreel.mp4", deterministicBriefing.Broadcast.VideoMp4Href, System.StringComparison.Ordinal);
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
