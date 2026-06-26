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
        Assert.Contains(map.ReplaySteps, step => step.Turn == 1 && !string.IsNullOrWhiteSpace(step.Summary));
        Assert.Contains(map.ReplaySteps, step => step.Turn == 2 && !string.IsNullOrWhiteSpace(step.Label));
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
    public void BlackLedger_public_entry_route_redirects_to_the_stable_command_map_surface()
    {
        string publicLanding = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string manifest = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_LANDING_MANIFEST.yaml"));

        Assert.Contains("[HttpGet(\"/ledger\")]", publicLanding, StringComparison.Ordinal);
        Assert.Contains("=> Redirect(BuildLedgerMapEntryHref(turn, mode));", publicLanding, StringComparison.Ordinal);
        Assert.Contains("required_final_url_prefix: /ledger/map", manifest, StringComparison.Ordinal);
    }

    [Fact]
    public void BlackLedgerMap_view_mounts_real_globe_at_anchor_instead_of_legacy_svg_fallback()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Ledger.cshtml"));

        Assert.Contains("id=\"ledger-map\"", view, StringComparison.Ordinal);
        Assert.Contains("data-black-ledger-geoscape-root", view, StringComparison.Ordinal);
        Assert.Contains("data-variant=\"full\"", view, StringComparison.Ordinal);
        Assert.Contains("data-map-url=\"/api/v1/ledger/worlds/emerald-sprawl-prelude/map", view, StringComparison.Ordinal);
        Assert.DoesNotContain("tactical fallback map", view, StringComparison.Ordinal);
        Assert.DoesNotContain("<svg viewBox=\"0 0 1200 760\"", view, StringComparison.Ordinal);
        Assert.DoesNotContain("<p class=\"editorial-copy\"></p>", view, StringComparison.Ordinal);
    }

    [Fact]
    public void BlackLedgerMap_view_keeps_one_dispatch_entry_and_terse_optional_viewer_copy()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Ledger.cshtml"));

        Assert.Contains("UndetectableHumanizerCopyAdapter.HumanizeLedger(Model.SecondaryAction.Label)", view, StringComparison.Ordinal);
        Assert.DoesNotContain("<strong>Read dispatches</strong>", view, StringComparison.Ordinal);
        Assert.Contains("<strong>Open newsroom</strong>", view, StringComparison.Ordinal);
        Assert.Contains("Optional viewer exports.", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Optional external viewer links stay here. The live board stays on this command map.", view, StringComparison.Ordinal);
        Assert.Contains("Turn 1 board", view, StringComparison.Ordinal);
        Assert.Contains("Awakened pressure", view, StringComparison.Ordinal);
        Assert.DoesNotContain("MysAd Density", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Logos, backdrops, score ledgers", view, StringComparison.Ordinal);
    }

    [Fact]
    public void BlackLedgerMap_view_keeps_command_deck_overlay_and_briefing_contracts()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Ledger.cshtml"));
        string css = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "css", "site.css"));
        string script = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "js", "black-ledger-geoscape.js"));

        Assert.Contains("data-overlay-eyebrow=\"Seattle command deck\"", view, StringComparison.Ordinal);
        Assert.Contains("data-overlay-headline=\"Track who is moving first.\"", view, StringComparison.Ordinal);
        Assert.Contains("data-signal-primary=\"district heat live\"", view, StringComparison.Ordinal);
        Assert.Contains("ledger-flagship__briefing", view, StringComparison.Ordinal);
        Assert.Contains("ledger-flagship__briefing-card", view, StringComparison.Ordinal);
        Assert.Contains("Watch the city breathe, see which bloc is leaning on which district", view, StringComparison.Ordinal);
        Assert.Contains(".ledger-flagship__briefing", css, StringComparison.Ordinal);
        Assert.Contains(".ledger-flagship__briefing-card", css, StringComparison.Ordinal);
        Assert.Contains("data-geoscape-stage", script, StringComparison.Ordinal);
        Assert.Contains("data-geoscape-overlay", script, StringComparison.Ordinal);
        Assert.Contains("data-geoscape-signal-rail", script, StringComparison.Ordinal);
        Assert.Contains("data-geoscape-panel", script, StringComparison.Ordinal);
        Assert.Contains("Preparing faction view.", script, StringComparison.Ordinal);
        Assert.Contains("Loading city map…", script, StringComparison.Ordinal);
        Assert.Contains("aria-label=\"Map views\"", script, StringComparison.Ordinal);
        Assert.Contains("aria-label=\"Accessible city list\"", script, StringComparison.Ordinal);
        Assert.Contains("District borders, pressure arrows, and turn replay stay visible.", script, StringComparison.Ordinal);
        Assert.Contains("} view`", script, StringComparison.Ordinal);
        Assert.DoesNotContain("Preparing faction posture.", script, StringComparison.Ordinal);
        Assert.DoesNotContain("Loading geoscape…", script, StringComparison.Ordinal);
        Assert.DoesNotContain("aria-label=\"Geoscape modes\"", script, StringComparison.Ordinal);
        Assert.DoesNotContain("aria-label=\"Accessible geoscape list\"", script, StringComparison.Ordinal);
        Assert.DoesNotContain("Faction countries, pressure arrows, and turn replay stay visible.", script, StringComparison.Ordinal);
        Assert.DoesNotContain("} lane`", script, StringComparison.Ordinal);
        Assert.Contains("--ledger-geoscape-panel-width", css, StringComparison.Ordinal);
        Assert.Contains(".ledger-flagship__geoscape-wrap > .ledger-flagship__geoscape.black-ledger-geoscape .black-ledger-geoscape__signal-rail", css, StringComparison.Ordinal);
        Assert.Contains("this.overlayEyebrow = root.dataset.overlayEyebrow", script, StringComparison.Ordinal);
        Assert.Contains("this.primarySignalLabel = root.dataset.signalPrimary", script, StringComparison.Ordinal);
    }

    [Fact]
    public void BlackLedgerMap_geoscape_script_draws_faction_country_borders_from_region_polygons()
    {
        string script = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "js", "black-ledger-geoscape.js"));
        string css = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "css", "site.css"));

        Assert.Contains("black-ledger-video-globe-idle.mp4", script, StringComparison.Ordinal);
        Assert.Contains("black-ledger-video-globe-idle.webm", script, StringComparison.Ordinal);
        Assert.Contains("black-ledger-video-globe-idle-poster.png", script, StringComparison.Ordinal);
        Assert.DoesNotContain("magicfit-primary", script, StringComparison.Ordinal);
        Assert.DoesNotContain("magicfit-video-globe-with-chummer-overlays", script, StringComparison.Ordinal);
        Assert.Contains("first-party-raster-overlay", script, StringComparison.Ordinal);
        Assert.Contains("EARTH_LANDMASSES", script, StringComparison.Ordinal);
        Assert.Contains("EARTH_MOUNTAIN_RANGES", script, StringComparison.Ordinal);
        Assert.Contains("getContext('webgl'", script, StringComparison.Ordinal);
        Assert.Contains("createEarthTexture", script, StringComparison.Ordinal);
        Assert.Contains("renderWebGlBase", script, StringComparison.Ordinal);
        Assert.Contains("webglcontextlost", script, StringComparison.Ordinal);
        Assert.Contains("webglcontextrestored", script, StringComparison.Ordinal);
        Assert.Contains("createEarthTexture", script, StringComparison.Ordinal);
        Assert.Contains("renderWebGlBase", script, StringComparison.Ordinal);
        Assert.Contains("drawingBufferWidth", script, StringComparison.Ordinal);
        Assert.Contains("window.addEventListener('resize', this.handleResize", script, StringComparison.Ordinal);
        Assert.Contains("drawLandmasses", script, StringComparison.Ordinal);
        Assert.Contains("drawMountainRanges", script, StringComparison.Ordinal);
        Assert.Contains("parseRegionPolygon", script, StringComparison.Ordinal);
        Assert.Contains("region.polygonPoints", script, StringComparison.Ordinal);
        Assert.Contains("drawFactionCountry", script, StringComparison.Ordinal);
        Assert.Contains("countryShapes", script, StringComparison.Ordinal);
        Assert.DoesNotContain("svg_tactical", script, StringComparison.Ordinal);
        Assert.Contains(".black-ledger-geoscape[data-video-globe=\"ready\"] .black-ledger-geoscape__video-plate", css, StringComparison.Ordinal);
        Assert.Contains("opacity: 0.94", css, StringComparison.Ordinal);
        Assert.DoesNotContain("opacity: 0.24", css, StringComparison.Ordinal);
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
