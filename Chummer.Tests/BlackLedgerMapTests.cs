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
        Assert.Equal("earth_globe_country_borders", map.RenderMode);
        Assert.Contains("bordered countries", map.AccessibilityNote, StringComparison.OrdinalIgnoreCase);
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
        Assert.Equal("earth_globe_country_borders", map.Projection);
        Assert.NotEmpty(map.Regions);
        Assert.All(map.Regions, region => Assert.False(string.IsNullOrWhiteSpace(region.PolygonPoints)));
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
        Assert.Contains("[HttpGet(\"/ledger/turns/{turn}/newsreel.json\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/ledger/worldtick/validation\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/ledger/factions/{factionId}/leader-briefing\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"worlds/{worldId}/map\")]", ledgerApi, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"worlds/{worldId}/map/turns/{turn:int}\")]", ledgerApi, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"worlds/{worldId}/map/tick-delta/{fromTurn:int}/{toTurn:int}\")]", ledgerApi, StringComparison.Ordinal);
    }

    [Fact]
    public void BlackLedgerMap_view_mounts_real_globe_at_anchor_instead_of_legacy_svg_fallback()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Ledger.cshtml"));

        Assert.Contains("id=\"ledger-map\"", view, StringComparison.Ordinal);
        Assert.Contains("The public globe route now lands on the real earth view", view, StringComparison.Ordinal);
        Assert.DoesNotContain("tactical fallback map", view, StringComparison.Ordinal);
        Assert.DoesNotContain("<svg viewBox=\"0 0 1200 760\"", view, StringComparison.Ordinal);
    }

    [Fact]
    public void BlackLedgerMap_geoscape_script_draws_faction_country_borders_from_region_polygons()
    {
        string script = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "js", "black-ledger-geoscape.js"));

        Assert.Contains("EARTH_LANDMASSES", script, StringComparison.Ordinal);
        Assert.Contains("EARTH_MOUNTAIN_RANGES", script, StringComparison.Ordinal);
        Assert.Contains("getContext('webgl'", script, StringComparison.Ordinal);
        Assert.Contains("createEarthTexture", script, StringComparison.Ordinal);
        Assert.Contains("renderWebGlBase", script, StringComparison.Ordinal);
        Assert.Contains("drawLandmasses", script, StringComparison.Ordinal);
        Assert.Contains("drawMountainRanges", script, StringComparison.Ordinal);
        Assert.Contains("parseRegionPolygon", script, StringComparison.Ordinal);
        Assert.Contains("region.polygonPoints", script, StringComparison.Ordinal);
        Assert.Contains("drawFactionCountry", script, StringComparison.Ordinal);
        Assert.Contains("countryShapes", script, StringComparison.Ordinal);
        Assert.DoesNotContain("svg_tactical", script, StringComparison.Ordinal);
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
