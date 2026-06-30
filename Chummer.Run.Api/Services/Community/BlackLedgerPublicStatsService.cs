using Chummer.Run.Api.ViewModels;
using Microsoft.Extensions.Configuration;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace Chummer.Run.Api.Services.Community;

public sealed class BlackLedgerPublicStatsService
{
    private const string SeedRelativePath = "black-ledger/worlds/emerald-sprawl-prelude.yaml";
    private static readonly string[] ForbiddenPublicTerms =
    [
        "productlift",
        "emailit",
        "deftform",
        "icanpreneur",
        "webhook secret",
        "chummer_",
        "support_case",
        "private_campaign",
        "account_email",
        "operator_secret",
        "sourcebook_text",
    ];
    private static readonly IDeserializer Deserializer = new DeserializerBuilder()
        .WithNamingConvention(UnderscoredNamingConvention.Instance)
        .WithDuplicateKeyChecking()
        .IgnoreUnmatchedProperties()
        .Build();
    private static readonly BlackLedgerPublicStatViewModel[] FallbackPreviewStats =
    [
        CreatePublicStat(
            id: "mysad-density",
            title: "MysAd density",
            value: "Ashline Circle 39%",
            period: "Turn 1",
            sampleSize: "6 seeded factions / 8 districts",
            sampleCount: 6,
            confidenceKey: "seeded",
            confidence: "Seeded",
            privacyNote: "Aggregate city view",
            sourceKind: "seeded_board",
            sourceLabel: "Canonical seed world",
            sourceSummary: "Derived from the canonical Emerald Sprawl world seed before any live campaign aggregation is allowed.",
            status: "seeded",
            href: "/ledger/stats#mysad-density"),
        CreatePublicStat(
            id: "debt-heat",
            title: "Debt Heat",
            value: "Rust Bazaar 99 heat",
            period: "Turn 1",
            sampleSize: "Canonical seed world",
            sampleCount: 8,
            confidenceKey: "seeded",
            confidence: "Seeded",
            privacyNote: "Fictional runner/campaign statistics only",
            sourceKind: "seeded_board",
            sourceLabel: "Canonical seed world",
            sourceSummary: "Computed from the canonical seeded faction and district model, not from private campaign telemetry.",
            status: "seeded",
            href: "/ledger/stats#debt-heat"),
        CreatePublicStat(
            id: "package-pressure",
            title: "Package pressure",
            value: "7 hot package candidates",
            period: "Turn 1",
            sampleSize: "3 candidate lanes",
            sampleCount: 3,
            confidenceKey: "seeded",
            confidence: "Seeded",
            privacyNote: "Demand signal, not a ship promise",
            sourceKind: "package_registry",
            sourceLabel: "Package registry pressure lanes",
            sourceSummary: "Summarizes package-pressure lanes without turning demand into a ship promise.",
            status: "seeded",
            href: "/ledger/packages"),
        CreatePublicStat(
            id: "chaos-index",
            title: "Chaos index",
            value: "Rust Bazaar heat 77",
            period: "Turn 1",
            sampleSize: "8 seeded districts",
            sampleCount: 8,
            confidenceKey: "seeded",
            confidence: "Seeded",
            privacyNote: "Playful fictional labels only; never point at real people.",
            sourceKind: "seeded_board",
            sourceLabel: "Canonical seed world",
            sourceSummary: "Uses fictional district heat from the Emerald Sprawl board.",
            status: "seeded",
            href: "/ledger/factions#chaos-index"),
    ];

    private static readonly BlackLedgerModuleViewModel[] Modules =
    [
        new("faction-intel", "Faction Intel", "Read faction pressure without exposing private tables or runner identities.", "/ledger/factions", "Opt-in aggregate"),
        new("runner-archetypes", "Runner Archetype Stats", "See archetype pressure, chrome load, and role-shift signals as publishable aggregates.", "/ledger/stats", "Seeded board"),
        new("package-pressure", "Package Pressure", "Track followed package demand and compatibility heat without claiming shipped status early.", "/ledger/packages", "Governed watch"),
        new("karma-forge-candidates", "Karma Forge Candidate Feed", "See which discovery lanes are generating governed package candidates and closeout motion.", "/karma-forge", "Discovery-linked"),
        new("closeout-feed", "Closeout Feed", "Follow reviewed closeout motion after it is ready for the public board.", "/ledger/closeouts", "Reviewed only"),
    ];

    private static readonly BlackLedgerCloseoutViewModel[] Closeouts =
    [
        new("Last turn summary", "Turn 1 already ran, and the first seeded board stays visible before any human steward takes over.", "/ledger/closeouts", "Public-safe board"),
        new("Closeout witness feed", "Reviewed closeout updates only appear after package, route, and release status all agree.", "/ledger/closeouts", "Reviewed only"),
        new("Package recovery watch", "Recovery and rollback posture stays visible without implying promoted shipment.", "/packages", "Governed watch"),
        new("Karma Forge dispatch", "Discovery packets can point at candidate motion, but not shipped status, until release status is current.", "/karma-forge", "Signal only"),
    ];
    private static readonly BlackLedgerWorldPreviewViewModel FallbackWorldPreview = new(
        WorldId: "emerald-sprawl-prelude",
        PublicName: "Emerald Sprawl: First Pressure",
        Status: "preseeded_preview",
        CurrentTurn: 1,
        TurnHeadline: "Turn 1 already ran. Debt Heat rose in Rust Bazaar while Ashline MysAd density pushed package pressure toward awakened build support.",
        SafetyNote: "Fictional city board only. The Ledger explains pressure, not people.",
        MapNote: "Globe view keeps faction pressure, package heat, and closeout motion readable without exposing private tables.",
        DeterministicPreview: false,
        TurnNavigation:
        [
            new(1, "Turn 1 live board", "/ledger?turn=1", true, false),
            new(2, "Turn 2 preview board", "/ledger?turn=2", false, true),
        ],
        Districts:
        [
            new("glass-heights", "Glass Heights", "520,80 760,70 850,210 790,330 560,300 470,190", "glass tower compact", 71, 34, "Glass Heights is led by glass tower compact with influence 71 and heat 34.", 658, 197, 82, 21, "stable", 0),
            new("rust-bazaar", "Rust Bazaar", "390,390 620,340 730,520 650,690 420,650 310,500", "rust market syndicate", 68, 77, "Rust Bazaar is led by rust market syndicate with influence 68 and heat 77.", 520, 515, 76, 74, "rising", 8),
            new("ashline-ward", "Ashline Ward", "820,180 1080,160 1130,340 990,500 800,430 760,300", "ashline circle", 64, 52, "Ashline Ward is led by ashline circle with influence 64 and heat 52.", 930, 318, 69, 57, "rising", 5),
            new("neon-docks", "Neon Docks", "60,260 300,210 390,390 310,500 130,520 40,400", "neon docks union", 73, 49, "Neon Docks is led by neon docks union with influence 73 and heat 49.", 205, 380, 78, 49, "rising", 4),
            new("ghostline-east", "Ghostline East", "850,500 1030,500 1160,620 1100,735 820,700 650,690", "ghostline network", 58, 41, "Ghostline East is led by ghostline network with influence 58 and heat 41.", 935, 624, 73, 38, "stable", 6),
            new("free-ward", "Free Ward", "120,520 310,500 420,650 350,735 90,730 40,630", "barrens free wardens", 61, 69, "Free Ward is led by barrens free wardens with influence 61 and heat 69.", 222, 627, 67, 66, "rising", 3),
            new("transit-spine", "Transit Spine", "300,210 470,190 560,300 620,340 390,390", "contested", 43, 56, "Transit Spine is contested with influence 43 and heat 56.", 468, 286, 55, 81, "volatile", 2),
            new("old-signal-loop", "Old Signal Loop", "760,300 800,430 850,500 650,690 730,520 620,340", "contested", 39, 62, "Old Signal Loop is contested with influence 39 and heat 62.", 735, 463, 51, 84, "volatile", 6),
        ],
        Factions:
        [
            new("glass_tower_compact", "Glass Tower Compact", "corporate-facing brokers", "glass director", "contract referee", "ledger notary", ["permit leverage 88", "public trust 51", "debt heat 42"], "#5ce2ff", "#89a7ff", "grid"),
            new("rust_market_syndicate", "Rust Market Syndicate", "gear/debt logistics", "rust broker", "debt clock", "receipt hawk", ["debt heat 99", "favor load 86", "package pressure 83"], "#ff8a3d", "#ff5d73", "credit-chip-broken"),
            new("ashline_circle", "Ashline Circle", "mystic-adjacent street coalition", "ashline seer", "drain keeper", "ritual scribe", ["drain pressure 72", "source clarity 48", "mystic density 39"], "#9c6cff", "#ffb84d", "ritual-eye"),
            new("neon_docks_union", "Neon Docks Union", "riggers and logistics crews", "dock boss", "route dispatcher", "container oracle", ["route control 76", "vehicle demand 75", "drone herd size 64"], "#63f2b6", "#5ce2ff", "cargo-node"),
            new("ghostline_network", "Ghostline Network", "intel and matrix rumor verification", "ghost handler", "signal referee", "redaction spider", ["intel volume 82", "false signal suppression 80", "signal confidence 67"], "#a9b8cf", "#5ce2ff", "signal-mask"),
            new("barrens_free_wardens", "Barrens Free Wardens", "street-level mutual protection", "warden marshal", "survival clock", "closeout witness", ["survival pressure 81", "attrition risk 63", "street witnesses 36"], "#ffb84d", "#63f2b6", "ward-shield"),
        ],
        StewardshipPosts:
        [
            new("ledger_gm", "Ledger GM", "interim", "interim ledger architect", "Runs the public world-turn shell until verified human stewards take over.", true),
            new("public_intel_provider", "Public Intel Provider", "interim", "public intel provider", "Turns world movement into public-safe summaries without leaking private administrative data.", true),
            new("package_pressure_analyst", "Package Pressure Analyst", "interim", "package factor", "Explains package demand as governed pressure, not shipped truth.", true),
            new("privacy_marshal", "Privacy Marshal", "interim", "privacy marshal", "Blocks private, identifying, sourcebook, support, or administrative data from public rendering.", true),
            new("closeout_clerk", "Closeout Clerk", "interim", "closeout clerk", "Keeps closeout movement tied to first-party turn records before it appears publicly.", true),
        ],
        StewardshipTransferPreview: new(
            "stewardship_transfer",
            "ledger_gm",
            "interim_ledger_architect",
            "verified_human_steward_pending",
            "human",
            "2026-05-14T12:00:00Z",
            "Handoff receipt proves that verified human stewardship outranks interim placeholders.",
            "stewarding_operator",
            "public_safe"),
        LastTick: new(
            "emerald-sprawl-prelude",
            1,
            "ledger_tick_0001_preseeded",
            "preseeded",
            "Debt Heat rises while Ashline MysAd density pulls package pressure toward awakened build support.",
            ComputeHash("emerald-sprawl-prelude:0:seeded_initial_state:input"),
            ComputeHash("emerald-sprawl-prelude:1:preseeded:decision"),
            true,
            Array.Empty<string>(),
            ComputeHash("emerald-sprawl-prelude:1:preseeded_tick_complete:output"),
            "2026-05-14T12:00:00Z",
            [
                new("rust market syndicate", "debt heat", 8, "Old favors were called in after a failed gear reconciliation."),
                new("ashline circle", "mysad density", 5, "Awakened build demand increased after a visible source-clarity dispute."),
                new("neon docks union", "vehicle package demand", 4, "Cargo-route pressure created demand for drone and vehicle overlays."),
                new("ghostline network", "false signal suppression", 6, "Ghostline filtered two rumor lanes before they became package truth."),
                new("barrens free wardens", "closeout witnesses", 3, "Two public-safe table outcomes were recorded as closeout witnesses."),
                new("glass tower compact", "public trust", -4, "License polish increased but public confidence fell after a quiet contract sweep."),
            ]));
    private readonly IConfiguration? _configuration;
    private readonly Lazy<BlackLedgerWorldSeedDocument?> _seedDocument;

    public BlackLedgerPublicStatsService(IConfiguration? configuration = null)
    {
        _configuration = configuration;
        _seedDocument = new Lazy<BlackLedgerWorldSeedDocument?>(
            LoadSeedDocumentCore,
            LazyThreadSafetyMode.ExecutionAndPublication);
    }

    public IReadOnlyList<BlackLedgerPublicStatViewModel> ListHomepageStats()
        => ListPublicStats().Take(3).ToArray();

    public IReadOnlyList<BlackLedgerPublicStatViewModel> ListPublicStats(int? requestedTurn = null)
    {
        BlackLedgerWorldSeedDocument? seed = TryLoadSeed();
        IReadOnlyList<BlackLedgerPublicStatViewModel> stats = seed is null
            ? FallbackPreviewStats
            : BuildSeedBackedStats(seed, requestedTurn);
        int minimumLiveSampleSize = seed?.PublicSafety?.MinSampleSizeForLivePublicStats ?? 10;
        return stats.Where(stat => IsPublicSafe(stat, minimumLiveSampleSize)).ToArray();
    }

    public IReadOnlyList<BlackLedgerModuleViewModel> ListModules()
        => Modules;

    public IReadOnlyList<BlackLedgerCloseoutViewModel> ListCloseouts()
        => Closeouts;

    public BlackLedgerWorldPreviewViewModel? LoadWorldPreview(int? requestedTurn = null)
    {
        BlackLedgerWorldSeedDocument? seed = TryLoadSeed();
        return seed is null ? FallbackWorldPreview : BuildWorldPreview(seed, requestedTurn);
    }

    public BlackLedgerCommandMapViewModel? LoadCommandMap(int? requestedTurn = null, string currentMode = "influence")
    {
        BlackLedgerWorldPreviewViewModel? world = LoadWorldPreview(requestedTurn);
        if (world is null || world.LastTick is null)
        {
            return null;
        }

        string normalizedMode = NormalizeMode(currentMode);
        var modes = BuildMapModes(normalizedMode);
        var events = BuildMapEvents(world);
        var arcs = BuildMapArcs(world);
        BlackLedgerWorldSeedDocument? seed = TryLoadSeed();
        var replaySteps = BuildReplaySteps(world, seed);

        return new BlackLedgerCommandMapViewModel(
            WorldId: world.WorldId,
            RenderMode: "earth_globe_country_borders",
            CurrentMode: normalizedMode,
            Modes: modes,
            Events: events,
            Arcs: arcs,
            ReplaySteps: replaySteps,
            AccessibilityNote: "Keyboard focus, button-based mode switching, and a region/event list fallback stay available even when motion is reduced. Faction territory stays readable as bordered countries instead of abstract blobs.",
            PerformanceNote: "The homepage globe stays bounded, responsive, and flagship-grade while drawing a real earth surface with faction-country borders from route-backed region polygons.",
            PublicSafetyNote: world.SafetyNote);
    }

    public BlackLedgerMapApiDocument? LoadCommandMapDocument(int? requestedTurn = null, string currentMode = "influence")
    {
        BlackLedgerWorldPreviewViewModel? world = LoadWorldPreview(requestedTurn);
        BlackLedgerCommandMapViewModel? commandMap = LoadCommandMap(requestedTurn, currentMode);
        if (world is null || commandMap is null || world.LastTick is null)
        {
            return null;
        }

        return new BlackLedgerMapApiDocument(
            WorldId: world.WorldId,
            DisplayName: world.PublicName,
            CurrentTurn: world.CurrentTurn,
            Projection: commandMap.RenderMode,
            CurrentMode: commandMap.CurrentMode,
            SafetyNote: world.SafetyNote,
            MapNote: world.MapNote,
            Regions: world.Districts.Select(static district => new BlackLedgerMapRegionApiDocument(
                RegionId: district.Id,
                Name: district.Name,
                PolygonPoints: district.PolygonPoints,
                DominantFactionId: NormalizeSlug(district.DominantFaction),
                Influence: district.Influence,
                Heat: district.Heat,
                Confidence: district.Confidence,
                Volatility: district.Volatility,
                Trend: district.Trend,
                DeltaSinceLastTick: district.DeltaSinceLastTick,
                CenterX: district.CenterX,
                CenterY: district.CenterY,
                Summary: district.Summary)).ToArray(),
            Factions: world.Factions.Select(static faction => new BlackLedgerMapFactionApiDocument(
                FactionId: faction.Id,
                Name: faction.PublicName,
                PublicSummary: string.Join(" · ", faction.PublicSignals),
                ColorPrimary: faction.ColorPrimary,
                ColorSecondary: faction.ColorSecondary,
                Icon: faction.Icon,
                Type: faction.Type)).ToArray(),
            Events: commandMap.Events.Select(static item => new BlackLedgerMapEventApiDocument(
                EventId: item.EventId,
                EventType: item.EventType,
                RegionId: item.RegionId,
                Severity: item.Severity,
                Confidence: item.Confidence,
                Status: item.Status,
                Turn: 1,
                SourceReceiptId: item.SourceReceiptId,
                DispatchHref: item.DispatchHref,
                Title: item.Title,
                Summary: item.Summary,
                X: item.X,
                Y: item.Y,
                NewThisTurn: item.NewThisTurn)).ToArray(),
            Arcs: commandMap.Arcs.Select(static item => new BlackLedgerMapArcApiDocument(
                ArcId: item.ArcId,
                SourceRegionId: item.SourceRegionId,
                TargetRegionId: item.TargetRegionId,
                ArcType: item.ArcType,
                Intensity: item.Intensity,
                Direction: item.Direction,
                Summary: item.Summary)).ToArray(),
            Modes: commandMap.Modes,
            ReplaySteps: commandMap.ReplaySteps,
            LatestTick: world.LastTick);
    }

    public BlackLedgerTickDeltaApiDocument? LoadTickDelta(int fromTurn, int toTurn)
    {
        if (fromTurn < 0 || toTurn < 0 || toTurn < fromTurn)
        {
            return null;
        }

        BlackLedgerWorldPreviewViewModel? world = LoadWorldPreview(toTurn);
        BlackLedgerCommandMapViewModel? commandMap = LoadCommandMap(toTurn);
        if (world is null || commandMap is null || world.LastTick is null)
        {
            return null;
        }

        return new BlackLedgerTickDeltaApiDocument(
            WorldId: world.WorldId,
            FromTurn: fromTurn,
            ToTurn: toTurn,
            Summary: world.LastTick.Summary,
            RegionDeltas: world.Districts
                .Where(static district => district.DeltaSinceLastTick != 0)
                .Select(static district => new BlackLedgerRegionDeltaApiDocument(
                    RegionId: district.Id,
                    Name: district.Name,
                    DeltaSinceLastTick: district.DeltaSinceLastTick,
                    Trend: district.Trend,
                    Heat: district.Heat,
                    Influence: district.Influence))
                .ToArray(),
            EventIds: commandMap.Events.Where(static item => item.NewThisTurn).Select(static item => item.EventId).ToArray(),
            ArcIds: commandMap.Arcs.Select(static item => item.ArcId).ToArray(),
            DispatchIds: ListDispatches(toTurn).Select(static item => item.DispatchId).ToArray());
    }

    public IReadOnlyList<BlackLedgerDispatchViewModel> ListDispatches(int? requestedTurn = null, string? factionId = null)
    {
        BlackLedgerWorldSeedDocument? seed = TryLoadSeed();
        if (seed is not null && GetDispatchDocuments(seed, requestedTurn).Count > 0)
        {
            IEnumerable<BlackLedgerDispatchViewModel> projectedDispatches = GetDispatchDocuments(seed, requestedTurn)
                .Select(ToViewModel);
            if (!string.IsNullOrWhiteSpace(factionId))
            {
                string normalized = NormalizeSlug(factionId);
                projectedDispatches = projectedDispatches.Where(item => item.InvolvedFactions.Any(faction =>
                    NormalizeSlug(faction).Equals(normalized, StringComparison.OrdinalIgnoreCase)));
            }

            return projectedDispatches.ToArray();
        }

        BlackLedgerWorldPreviewViewModel? world = LoadWorldPreview(requestedTurn);
        if (world?.LastTick is null)
        {
            return Array.Empty<BlackLedgerDispatchViewModel>();
        }

        IEnumerable<BlackLedgerDispatch> dispatches = BuildDispatchRecords(world);
        if (!string.IsNullOrWhiteSpace(factionId))
        {
            dispatches = dispatches.Where(item => item.InvolvedFactions.Any(faction =>
                NormalizeSlug(faction).Equals(NormalizeSlug(factionId), StringComparison.OrdinalIgnoreCase)));
        }

        return dispatches.Select(ToViewModel).ToArray();
    }

    public BlackLedgerDispatchViewModel? LoadDispatch(string dispatchId, int? requestedTurn = null, string? factionId = null)
    {
        BlackLedgerDispatchViewModel? dispatch = ListDispatches(requestedTurn, factionId)
            .FirstOrDefault(item => string.Equals(item.DispatchId, dispatchId, StringComparison.OrdinalIgnoreCase));
        if (dispatch is not null || requestedTurn.HasValue)
        {
            return dispatch;
        }

        int? inferredTurn = TryInferTurnFromDispatchId(dispatchId);
        return inferredTurn.HasValue
            ? ListDispatches(inferredTurn.Value, factionId)
                .FirstOrDefault(item => string.Equals(item.DispatchId, dispatchId, StringComparison.OrdinalIgnoreCase))
            : null;
    }

    private static int? TryInferTurnFromDispatchId(string? dispatchId)
    {
        if (string.IsNullOrWhiteSpace(dispatchId))
        {
            return null;
        }

        Match match = Regex.Match(dispatchId, @"(?:^|_)turn_(\d{1,6})(?:_|$)", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
        return match.Success && int.TryParse(match.Groups[1].Value, out int turn) && turn >= 0
            ? turn
            : null;
    }

    public BlackLedgerWorldSeedDocument? LoadSeedDocument()
        => TryLoadSeed();

    private BlackLedgerWorldSeedDocument? TryLoadSeed()
        => _seedDocument.Value;

    private BlackLedgerWorldSeedDocument? LoadSeedDocumentCore()
    {
        foreach (string path in ResolveSeedPathCandidates())
        {
            if (!File.Exists(path))
            {
                continue;
            }

            try
            {
                using var reader = File.OpenText(path);
                var document = Deserializer.Deserialize<BlackLedgerWorldSeedDocument>(reader);
                if (document is null || !IsWorldPublicSafe(document))
                {
                    return null;
                }

                return document;
            }
            catch
            {
                return null;
            }
        }

        return null;
    }

    private IEnumerable<string> ResolveSeedPathCandidates()
    {
        string? configured = _configuration?["CHUMMER_BLACK_LEDGER_SEED_PATH"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            yield return Path.GetFullPath(configured);
        }

        foreach (string root in ResolveRootCandidates())
        {
            yield return Path.Combine(root, SeedRelativePath.Replace('/', Path.DirectorySeparatorChar));
            yield return Path.Combine(root, "chummer-hub-registry", SeedRelativePath.Replace('/', Path.DirectorySeparatorChar));
        }
    }

    public DispatchEmailDigest? BuildDispatchEmailDigest(int? requestedTurn = null)
    {
        BlackLedgerDispatchViewModel? latest = ListDispatches(requestedTurn).FirstOrDefault();
        if (latest is null)
        {
            return null;
        }

        string excerpt = latest.Body.Split("\n\n", StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? latest.Summary;
        return new DispatchEmailDigest(
            DispatchId: latest.DispatchId,
            Title: latest.Title,
            Excerpt: excerpt,
            Highlights: latest.PackagePressureLinks.Count > 0
                ? latest.PackagePressureLinks.Select(static item => item.Trim()).Where(static item => item.Length > 0).ToArray()
                : Array.Empty<string>(),
            DispatchUrl: latest.Href,
            SourceReceiptUrl: latest.SourceReceiptHref,
            PrivacyNote: "From a public-safe dispatch.");
    }

    private static IReadOnlyList<BlackLedgerDispatch> BuildDispatchRecords(BlackLedgerWorldPreviewViewModel world)
    {
        BlackLedgerTickReceiptViewModel tick = world.LastTick ?? throw new InvalidOperationException("World preview is missing the last tick.");
        string turnLabel = $"Turn {tick.Turn}";
        string baseCreatedAt = tick.CreatedAtUtc;
        var dispatches = new List<BlackLedgerDispatch>
        {
            CreateDispatch(
                dispatchId: $"ledger_dispatch_{world.WorldId}_turn_{tick.Turn:0000}",
                worldId: world.WorldId,
                turn: tick.Turn,
                type: "turn_dispatch",
                title: $"{turnLabel} — The city is moving",
                summary: world.TurnHeadline,
                body:
                    $"Turn {tick.Turn} already ran.\n\n" +
                    $"{tick.Summary}\n\n" +
                    $"The Ledger marked the movement, not the people: faction pressure shifted, package demand moved, and closeout witnesses stayed tied to one receipt before any dispatch was allowed to talk.\n\n" +
                    $"Filed after {tick.ReceiptId}.",
                involvedFactions: world.Factions.Take(4).Select(static item => item.PublicName).ToArray(),
                involvedDistricts: world.Districts.Take(4).Select(static item => item.Name).ToArray(),
                packagePressureLinks: ["/ledger/packages", "/karma-forge"],
                sourceReceiptId: tick.ReceiptId,
                sourceReceiptHref: "/ledger/closeouts",
                createdAtUtc: baseCreatedAt),
        };

        dispatches.AddRange(BuildEffectDispatches(world, tick, turnLabel, baseCreatedAt));
        if (!dispatches.Any(item => item.DispatchId.Contains("drone_logistics", StringComparison.OrdinalIgnoreCase)))
        {
            dispatches.Add(
                CreateDispatch(
                    dispatchId: $"ledger_dispatch_{world.WorldId}_turn_{tick.Turn:0000}_drone_logistics_overlay",
                    worldId: world.WorldId,
                    turn: tick.Turn,
                    type: "package_pressure_dispatch",
                    title: "Drone Logistics Overlay — Candidate heat rising",
                    summary: "Useful route-and-drone pressure crossed from rumor to watched package signal.",
                    body:
                        "The requests were not glamorous: better cargo state, clearer drone loadouts, fewer lost handoffs. The Ledger marked it as boring, useful, and therefore dangerous to ignore.\n\n" +
                        $"Filed after {tick.ReceiptId}.",
                    involvedFactions: ["Neon Docks Union", "Ghostline Network"],
                    involvedDistricts: ["Neon Docks", "Old Signal Loop"],
                    packagePressureLinks: ["/ledger/packages", "/karma-forge"],
                    sourceReceiptId: tick.ReceiptId,
                    sourceReceiptHref: "/ledger/closeouts",
                    createdAtUtc: baseCreatedAt));
        }

        return dispatches;
    }

    private static IEnumerable<BlackLedgerDispatch> BuildEffectDispatches(
        BlackLedgerWorldPreviewViewModel world,
        BlackLedgerTickReceiptViewModel tick,
        string turnLabel,
        string createdAtUtc)
    {
        foreach (BlackLedgerTickEffectViewModel effect in tick.Effects)
        {
            string normalizedTarget = effect.Target.Trim().ToLowerInvariant();
            if (normalizedTarget.Contains("rust", StringComparison.Ordinal))
            {
                yield return CreateDispatch(
                    dispatchId: $"ledger_dispatch_{world.WorldId}_turn_{tick.Turn:0000}_rust_bazaar",
                    worldId: world.WorldId,
                    turn: tick.Turn,
                    type: "district_dispatch",
                    title: "The Rust Bazaar called in old favors.",
                    summary: "Debt markers moved first, and package pressure followed.",
                    body:
                        $"{effect.PublicReason}\n\n" +
                        "The Bazaar did not need names. Gear requests spiked, favors got counted twice, and the district made boring logistics feel dangerous again.\n\n" +
                        $"Filed after {tick.ReceiptId}.",
                    involvedFactions: ["Rust Market Syndicate"],
                    involvedDistricts: ["Rust Bazaar"],
                    packagePressureLinks: ["/ledger/packages"],
                    sourceReceiptId: tick.ReceiptId,
                    sourceReceiptHref: "/ledger/closeouts",
                    createdAtUtc: createdAtUtc);
                continue;
            }

            if (normalizedTarget.Contains("ashline", StringComparison.Ordinal))
            {
                yield return CreateDispatch(
                    dispatchId: $"ledger_dispatch_{world.WorldId}_turn_{tick.Turn:0000}_ashline_circle",
                    worldId: world.WorldId,
                    turn: tick.Turn,
                    type: "faction_dispatch",
                    title: "Ashline Circle — Source clarity dispute",
                    summary: "Awakened build demand rose because the paperwork stayed murkier than the intent.",
                    body:
                        $"{effect.PublicReason}\n\n" +
                        "The Circle did not argue about power. It argued about control. Clean intent with dirty paperwork pushed MysAd density upward and nudged package demand toward explainers instead of swagger.\n\n" +
                        $"Filed after {tick.ReceiptId}.",
                    involvedFactions: ["Ashline Circle"],
                    involvedDistricts: ["Ashline Ward"],
                    packagePressureLinks: ["/ledger/packages", "/karma-forge"],
                    sourceReceiptId: tick.ReceiptId,
                    sourceReceiptHref: "/ledger/closeouts",
                    createdAtUtc: createdAtUtc);
                continue;
            }

            if (normalizedTarget.Contains("neon", StringComparison.Ordinal))
            {
                yield return CreateDispatch(
                    dispatchId: $"ledger_dispatch_{world.WorldId}_turn_{tick.Turn:0000}_neon_docks",
                    worldId: world.WorldId,
                    turn: tick.Turn,
                    type: "district_dispatch",
                    title: "Neon Docks — Drone logistics pressure",
                    summary: "Cargo trouble turned into visible demand for route and drone overlays.",
                    body:
                        $"{effect.PublicReason}\n\n" +
                        "Containers moved, drones failed, and somebody's maintenance debt became everybody's routing problem. The Docks did not ask for attention. Package pressure did that for them.\n\n" +
                        $"Filed after {tick.ReceiptId}.",
                    involvedFactions: ["Neon Docks Union"],
                    involvedDistricts: ["Neon Docks"],
                    packagePressureLinks: ["/ledger/packages"],
                    sourceReceiptId: tick.ReceiptId,
                    sourceReceiptHref: "/ledger/closeouts",
                    createdAtUtc: createdAtUtc);
                continue;
            }

            if (normalizedTarget.Contains("ghostline", StringComparison.Ordinal))
            {
                yield return CreateDispatch(
                    dispatchId: $"ledger_dispatch_{world.WorldId}_turn_{tick.Turn:0000}_ghostline",
                    worldId: world.WorldId,
                    turn: tick.Turn,
                    type: "closeout_dispatch",
                    title: "Ghostline — Rumor lane suppressed",
                    summary: "Two rumor lanes died before they could pretend to be package truth.",
                    body:
                        $"{effect.PublicReason}\n\n" +
                        "Ghostline killed the noise before it touched the shelf. No heroics, no badges, just one less false truth for the table to trip over.\n\n" +
                        $"Filed after {tick.ReceiptId}.",
                    involvedFactions: ["Ghostline Network"],
                    involvedDistricts: ["Ghostline East", "Old Signal Loop"],
                    packagePressureLinks: ["/ledger/closeouts", "/ledger/packages"],
                    sourceReceiptId: tick.ReceiptId,
                    sourceReceiptHref: "/ledger/closeouts",
                    createdAtUtc: createdAtUtc);
            }
        }
    }

    private static BlackLedgerDispatch CreateDispatch(
        string dispatchId,
        string worldId,
        int turn,
        string type,
        string title,
        string summary,
        string body,
        IReadOnlyList<string> involvedFactions,
        IReadOnlyList<string> involvedDistricts,
        IReadOnlyList<string> packagePressureLinks,
        string sourceReceiptId,
        string sourceReceiptHref,
        string createdAtUtc)
        => new(
            DispatchId: dispatchId,
            WorldId: worldId,
            Turn: turn,
            Type: type,
            Scope: "public_safe_flagship_seeded_board",
            SourceReceiptId: sourceReceiptId,
            SourceReceiptHref: sourceReceiptHref,
            Title: title,
            Summary: summary,
            Body: body,
            InvolvedFactions: involvedFactions,
            InvolvedDistricts: involvedDistricts,
            PackagePressureLinks: packagePressureLinks,
            PrivacyStatus: "public_safe",
            GeneratedBy: "ai_seeded_dispatch_generator",
            HumanReviewStatus: "optional",
            CreatedAtUtc: createdAtUtc,
            PublicSafe: true,
            AiGenerated: true,
            Href: $"/ledger/dispatches/{dispatchId}");

    private static BlackLedgerDispatchViewModel ToViewModel(BlackLedgerDispatch dispatch)
        => new(
            DispatchId: dispatch.DispatchId,
            WorldId: dispatch.WorldId,
            Turn: dispatch.Turn,
            Type: dispatch.Type,
            Scope: dispatch.Scope,
            SourceReceiptId: dispatch.SourceReceiptId,
            SourceReceiptHref: dispatch.SourceReceiptHref,
            Title: dispatch.Title,
            Summary: dispatch.Summary,
            Body: dispatch.Body,
            InvolvedFactions: dispatch.InvolvedFactions,
            InvolvedDistricts: dispatch.InvolvedDistricts,
            PackagePressureLinks: dispatch.PackagePressureLinks,
            PrivacyStatus: dispatch.PrivacyStatus,
            GeneratedBy: dispatch.GeneratedBy,
            HumanReviewStatus: dispatch.HumanReviewStatus,
            CreatedAtUtc: dispatch.CreatedAtUtc,
            PublicSafe: dispatch.PublicSafe,
            AiGenerated: dispatch.AiGenerated,
            Href: dispatch.Href);

    private static BlackLedgerDispatchViewModel ToViewModel(BlackLedgerDispatchDocument dispatch)
        => new(
            DispatchId: dispatch.DispatchId,
            WorldId: dispatch.WorldId,
            Turn: dispatch.Turn,
            Type: string.IsNullOrWhiteSpace(dispatch.DispatchType) ? "dispatch" : dispatch.DispatchType,
            Scope: "public_safe_seed",
            SourceReceiptId: dispatch.SourceReceiptIds?.FirstOrDefault() ?? $"turn_{dispatch.Turn:0000}",
            SourceReceiptHref: "/ledger/turns/1",
            Title: dispatch.Title,
            Summary: dispatch.Summary,
            Body: dispatch.BodyMarkdown,
            InvolvedFactions: ResolveDispatchFactions(dispatch),
            InvolvedDistricts: ResolveDispatchDistricts(dispatch),
            PackagePressureLinks: ResolveDispatchPackageLinks(dispatch),
            PrivacyStatus: dispatch.PrivacyStatus,
            GeneratedBy: "seeded_public_projection",
            HumanReviewStatus: "optional",
            CreatedAtUtc: "2026-05-15T00:00:00Z",
            PublicSafe: dispatch.PublicProjectionAllowed && !dispatch.OfficialIpNamesPresent && !dispatch.SourcebookTextPresent,
            AiGenerated: true,
            Href: $"/ledger/dispatches/{dispatch.DispatchId}");

    private static string NormalizeSlug(string value)
        => value.Trim().ToLowerInvariant().Replace("_", "-", StringComparison.Ordinal).Replace(" ", "-", StringComparison.Ordinal);

    private static IEnumerable<string> ResolveRootCandidates()
    {
        var candidates = new List<string>
        {
            Directory.GetCurrentDirectory(),
            AppContext.BaseDirectory,
            Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."))
        };

        string? configuredRoots = Environment.GetEnvironmentVariable("CHUMMER_BLACK_LEDGER_ROOTS");
        if (!string.IsNullOrWhiteSpace(configuredRoots))
        {
            candidates.AddRange(Regex.Split(configuredRoots, "[,;:]").Where(static value => !string.IsNullOrWhiteSpace(value)));
        }

        foreach (string candidate in candidates
                     .Where(static value => !string.IsNullOrWhiteSpace(value))
                     .Select(static value => Path.GetFullPath(value))
                     .Distinct(StringComparer.OrdinalIgnoreCase))
        {
            yield return candidate;
        }
    }

    private static IReadOnlyList<BlackLedgerPublicStatViewModel> BuildSeedBackedStats(BlackLedgerWorldSeedDocument seed, int? requestedTurn)
    {
        var selectedTurn = SelectTurn(seed, requestedTurn);
        var currentTurn = selectedTurn.Turn;
        string period = currentTurn is null ? "Turn 0" : $"Turn {currentTurn.Turn}";
        var factions = GetFactionDocuments(seed);
        var districts = GetDistrictDocuments(seed);
        var packagePressure = GetPackagePressureDocuments(seed, currentTurn);
        var factionById = factions
            .Where(static faction => !string.IsNullOrWhiteSpace(GetFactionId(faction)))
            .ToDictionary(static faction => GetFactionId(faction), StringComparer.OrdinalIgnoreCase);
        var districtById = districts
            .Where(static district => !string.IsNullOrWhiteSpace(GetDistrictId(district)))
            .ToDictionary(static district => GetDistrictId(district), StringComparer.OrdinalIgnoreCase);
        var effects = (currentTurn?.Effects ?? [])
            .GroupBy(static effect => $"{effect.Target}:{effect.Metric}", StringComparer.OrdinalIgnoreCase)
            .ToDictionary(
                static group => group.Key,
                static group => group.Sum(static effect => effect.Delta),
                StringComparer.OrdinalIgnoreCase);

        int AdjustedStat(string factionId, string metric)
        {
            if (!factionById.TryGetValue(factionId, out var faction)
                || faction.Stats is null
                || !faction.Stats.TryGetValue(metric, out int value))
            {
                return 0;
            }

            effects.TryGetValue($"{factionId}:{metric}", out int delta);
            return value + delta;
        }

        string TopDistrictHeat()
        {
            var hottest = districts
                .OrderByDescending(static district => district.Heat)
                .FirstOrDefault();
            return hottest is null ? "Transit Spine heat 56" : $"{hottest.Name} heat {hottest.Heat}";
        }

        string TopPackagePressure()
        {
            int topPressure = packagePressure
                .Select(static package => package.Pressure)
                .DefaultIfEmpty(0)
                .Max();
            return $"{topPressure} hot package candidates";
        }

        string SeededFactionSample() => $"{factions.Count} seeded factions / {districts.Count} districts";

        int minimumLiveSampleSize = 10;
        string packagePressureConfidenceKey = packagePressure.Count >= minimumLiveSampleSize
            ? "enough_data"
            : "seeded";

        BlackLedgerPublicStatViewModel[] stats =
        [
            CreatePublicStat(
                id: "mysad-density",
                title: "MysAd density",
                value: $"Ashline Circle {AdjustedStat("ashline_circle", "mysad_density")}%",
                period: period,
                sampleSize: SeededFactionSample(),
                sampleCount: factions.Count,
                confidenceKey: "seeded",
                confidence: "Seeded",
                privacyNote: "Aggregate city view",
                sourceKind: "seeded_board",
                sourceLabel: "Canonical seed world",
                sourceSummary: "Derived from the Emerald Sprawl seed model until opted-in live data clears privacy thresholds.",
                status: "seeded",
                href: "/ledger/stats#mysad-density"),
            CreatePublicStat(
                id: "debt-heat",
                title: "Debt Heat",
                value: $"Rust Bazaar {AdjustedStat("rust_market_syndicate", "debt_heat")} heat",
                period: period,
                sampleSize: "Canonical seed world",
                sampleCount: districtById.Count,
                confidenceKey: "seeded",
                confidence: "Seeded",
                privacyNote: "Fictional runner/campaign statistics only",
                sourceKind: "seeded_board",
                sourceLabel: "Canonical seed world",
                sourceSummary: "Computed from the fictional city board, never from support or account-linked traffic.",
                status: "seeded",
                href: "/ledger/stats#debt-heat"),
            CreatePublicStat(
                id: "package-pressure",
                title: "Package pressure",
                value: TopPackagePressure(),
                period: period,
                sampleSize: $"{packagePressure.Count} candidate lanes",
                sampleCount: packagePressure.Count,
                confidenceKey: packagePressureConfidenceKey,
                confidence: packagePressureConfidenceKey == "enough_data" ? "Enough data" : "Seeded",
                privacyNote: "Demand signal, not a ship promise",
                sourceKind: "package_registry",
                sourceLabel: "Package registry pressure lanes",
                sourceSummary: "Uses the package-pressure lane set until opted-in live samples are large enough to publish.",
                status: "seeded",
                href: "/ledger/packages"),
            CreatePublicStat(
                id: "chaos-index",
                title: "Chaos index",
                value: TopDistrictHeat(),
                period: period,
                sampleSize: $"{districtById.Count} seeded districts",
                sampleCount: districtById.Count,
                confidenceKey: "seeded",
                confidence: "Seeded",
                privacyNote: "Playful fictional labels only; never point at real people.",
                sourceKind: "seeded_board",
                sourceLabel: "Canonical seed world",
                sourceSummary: "Uses district heat snapshots from the canonical public seed and blocks publication if the map becomes unsafe.",
                status: "seeded",
                href: "/ledger/factions#chaos-index"),
        ];

        return stats;
    }

    private static BlackLedgerWorldPreviewViewModel BuildWorldPreview(BlackLedgerWorldSeedDocument seed, int? requestedTurn)
    {
        var selectedTurn = SelectTurn(seed, requestedTurn);
        var currentTurn = selectedTurn.Turn;
        string turnHeadline = currentTurn is null
            ? "Turn 0 is loaded."
            : selectedTurn.IsDeterministicPreview
                ? $"Turn {currentTurn.Turn} preview board is ready. {currentTurn.Summary}"
                : currentTurn.Headline;
        string safetyNote = seed.SourcePolicy?.PublicCopyNote ?? "Canonical seeded board and aggregate city view only.";
        string mapNote = "Use the map to inspect districts, pressure arcs, and dispatches without exposing private tables.";
        var aiNames = GetAiPersonalities(seed)
            .Where(static personality => !string.IsNullOrWhiteSpace(GetPersonalityId(personality)))
            .ToDictionary(static personality => GetPersonalityId(personality), static personality => GetPersonalityLabel(personality), StringComparer.OrdinalIgnoreCase);
        var districts = GetDistrictDocuments(seed)
            .Select(district => new BlackLedgerDistrictViewModel(
                GetDistrictId(district),
                district.Name,
                string.Join(" ", (district.Polygon ?? []).Select(static point => point.Count >= 2 ? $"{point[0]},{point[1]}" : string.Empty).Where(static point => !string.IsNullOrWhiteSpace(point))),
                GetDominantFactionId(district).Replace('_', ' '),
                district.Influence,
                district.Heat,
                string.IsNullOrWhiteSpace(district.Summary) ? BuildDistrictSummary(district) : district.Summary,
                ComputePolygonCenter(district.Polygon).x,
                ComputePolygonCenter(district.Polygon).y,
                district.Confidence == 0 ? ComputeDistrictConfidence(district) : district.Confidence,
                district.Volatility == 0 ? ComputeDistrictVolatility(district) : district.Volatility,
                string.IsNullOrWhiteSpace(district.Trend) ? ComputeDistrictTrend(district) : district.Trend,
                district.DeltaSinceLastTick == 0 ? ComputeDistrictDelta(district) : district.DeltaSinceLastTick))
            .ToArray();
        var factions = GetFactionDocuments(seed)
            .Select(faction => new BlackLedgerFactionViewModel(
                GetFactionId(faction),
                faction.PublicName,
                string.IsNullOrWhiteSpace(faction.Archetype) ? faction.Type : faction.Archetype,
                ResolveAiName(aiNames, faction.ManagementPosts?.FactionLeader),
                ResolveAiName(aiNames, faction.ManagementPosts?.FieldGm),
                ResolveAiName(aiNames, faction.ManagementPosts?.IntelProvider),
                BuildFactionSignals(faction),
                string.IsNullOrWhiteSpace(faction.ColorPrimary) ? ResolveFactionVisual(GetFactionId(faction)).primary : faction.ColorPrimary,
                string.IsNullOrWhiteSpace(faction.ColorSecondary) ? ResolveFactionVisual(GetFactionId(faction)).secondary : faction.ColorSecondary,
                string.IsNullOrWhiteSpace(faction.Icon) ? ResolveFactionVisual(GetFactionId(faction)).icon : faction.Icon))
            .ToArray();
        BlackLedgerTickReceiptViewModel? lastTick = currentTurn is null || string.IsNullOrWhiteSpace(currentTurn.ReceiptId)
            ? null
            : new BlackLedgerTickReceiptViewModel(
                seed.WorldId,
                currentTurn.Turn,
                currentTurn.ReceiptId,
                selectedTurn.Mode,
                string.IsNullOrWhiteSpace(currentTurn.Headline) ? currentTurn.Summary : currentTurn.Headline,
                string.IsNullOrWhiteSpace(currentTurn.InputStateHash) ? ComputeHash($"{seed.WorldId}:{currentTurn.Turn - 1}:{currentTurn.State}:input") : currentTurn.InputStateHash,
                string.IsNullOrWhiteSpace(currentTurn.DecisionPacketHash) ? ComputeHash($"{seed.WorldId}:{currentTurn.Turn}:{string.Join('|', (currentTurn.Effects ?? []).Select(effect => $"{effect.Target}:{effect.Metric}:{effect.Delta}:{effect.PublicReason}"))}:decision") : currentTurn.DecisionPacketHash,
                !string.Equals(currentTurn.PrivacyResult?.Status, "failed", StringComparison.OrdinalIgnoreCase),
                currentTurn.PrivacyResult?.BlockedFields?.ToArray() ?? Array.Empty<string>(),
                string.IsNullOrWhiteSpace(currentTurn.OutputStateHash) ? ComputeHash($"{seed.WorldId}:{currentTurn.Turn}:{currentTurn.State}:output") : currentTurn.OutputStateHash,
                selectedTurn.CreatedAtUtc ?? "2026-05-14T12:00:00Z",
                (currentTurn.Effects ?? [])
                .Select(effect => new BlackLedgerTickEffectViewModel(
                    effect.Target.Replace('_', ' '),
                    effect.Metric.Replace('_', ' '),
                    effect.Delta,
                    effect.PublicReason))
                .ToArray());

        return new BlackLedgerWorldPreviewViewModel(
            seed.WorldId,
            seed.PublicName,
            seed.Status,
            currentTurn?.Turn ?? seed.CurrentTurn,
            turnHeadline,
            safetyNote,
            mapNote,
            selectedTurn.IsDeterministicPreview,
            BuildTurnNavigation(seed, currentTurn?.Turn ?? seed.CurrentTurn),
            districts,
            factions,
            BuildStewardshipPosts(seed),
            BuildStewardshipTransferPreview(seed),
            lastTick);
    }

    private static SelectedTurnContext SelectTurn(BlackLedgerWorldSeedDocument seed, int? requestedTurn)
    {
        BlackLedgerTurnDocument? publishedTurn;
        if (requestedTurn.HasValue)
        {
            publishedTurn = (seed.Turns ?? [])
                .Where(turn => turn.Turn == requestedTurn.Value)
                .OrderByDescending(static turn => turn.Turn)
                .FirstOrDefault();
            if (publishedTurn is null && requestedTurn.Value != 2)
            {
                return new SelectedTurnContext(
                    Turn: null,
                    IsDeterministicPreview: false,
                    Mode: "missing_turn",
                    CreatedAtUtc: null);
            }
        }
        else
        {
            publishedTurn = (seed.Turns ?? []).OrderByDescending(static turn => turn.Turn).FirstOrDefault();
        }
        if (requestedTurn == 2)
        {
            var deterministicTurn = seed.DeterministicTestTicks?
                .FirstOrDefault(static tick => tick.Turn == 2);
            if (deterministicTurn is not null)
            {
                return new SelectedTurnContext(
                    Turn: new BlackLedgerTurnDocument
                    {
                        Turn = deterministicTurn.Turn,
                        State = deterministicTurn.State,
                        Summary = deterministicTurn.Summary,
                        ReceiptId = deterministicTurn.ReceiptId,
                        Effects = deterministicTurn.Effects,
                        PackagePressure = deterministicTurn.PackagePressure,
                    },
                    IsDeterministicPreview: true,
                    Mode: "preseeded",
                    CreatedAtUtc: deterministicTurn.CreatedAtUtc);
            }
        }

        return new SelectedTurnContext(
            Turn: publishedTurn,
            IsDeterministicPreview: false,
            Mode: "preseeded",
            CreatedAtUtc: "2026-05-14T12:00:00Z");
    }

    private static IReadOnlyList<BlackLedgerTurnNavigationViewModel> BuildTurnNavigation(BlackLedgerWorldSeedDocument seed, int currentTurn)
        => (seed.Turns ?? [])
            .OrderBy(static turn => turn.Turn)
            .Select(turn => new BlackLedgerTurnNavigationViewModel(
                turn.Turn,
                string.IsNullOrWhiteSpace(turn.Headline) ? $"Turn {turn.Turn}" : turn.Headline,
                $"/ledger/turns/{turn.Turn}",
                currentTurn == turn.Turn,
                false))
            .ToArray();

    private static IReadOnlyList<BlackLedgerStewardshipPostViewModel> BuildStewardshipPosts(BlackLedgerWorldSeedDocument seed)
    {
        if (seed.GlobalPosts?.Count > 0)
        {
            var personalities = GetAiPersonalities(seed)
                .Where(static personality => !string.IsNullOrWhiteSpace(GetPersonalityId(personality)))
                .ToDictionary(static personality => GetPersonalityId(personality), StringComparer.OrdinalIgnoreCase);
            return seed.GlobalPosts
                .Select(post =>
                {
                    personalities.TryGetValue(post.FallbackPersonality ?? string.Empty, out var personality);
                    string fallback = string.IsNullOrWhiteSpace(post.FallbackPersonality)
                        ? "unassigned"
                        : post.FallbackPersonality.Replace('_', ' ');
                    string summary = post.PublicSummary;
                    if (personality?.Goals?.Any() == true)
                    {
                        summary = $"{summary} Current brief: {personality.Goals[0]}.";
                    }

                    return new BlackLedgerStewardshipPostViewModel(
                        post.Id,
                        post.PublicLabel,
                        post.HolderType,
                        fallback,
                        summary,
                        HumanOverrideAvailable: true);
                })
                .ToArray();
        }

        return GetAiPersonalities(seed)
            .Where(static personality => string.Equals(personality.Role, "global_ledger_gm", StringComparison.OrdinalIgnoreCase)
                || string.Equals(personality.Role, "global_privacy_gate", StringComparison.OrdinalIgnoreCase)
                || string.Equals(personality.Role, "global_closeout_materializer", StringComparison.OrdinalIgnoreCase)
                || string.Equals(personality.Role, "global_package_pressure", StringComparison.OrdinalIgnoreCase))
            .Select(personality => new BlackLedgerStewardshipPostViewModel(
                GetPersonalityId(personality),
                GetPersonalityLabel(personality),
                "ai",
                GetPersonalityId(personality),
                $"{GetPersonalityLabel(personality)} stays bounded to public-safe seeded world stewardship.",
                true))
            .ToArray();
    }

    private static BlackLedgerStewardshipTransferReceiptViewModel? BuildStewardshipTransferPreview(BlackLedgerWorldSeedDocument seed)
    {
        var receipt = seed.StewardshipTransferPreview;
        return receipt is null
            ? null
            : new BlackLedgerStewardshipTransferReceiptViewModel(
                receipt.ReceiptType,
                receipt.PostId,
                receipt.OldHolder,
                receipt.NewHolder,
                receipt.NewHolderType,
                receipt.OccurredAt,
                receipt.Reason,
                receipt.OperatorId,
                receipt.PublicVisibility);
    }

    private static string ResolveAiName(IReadOnlyDictionary<string, string> aiNames, string? id)
        => !string.IsNullOrWhiteSpace(id) && aiNames.TryGetValue(id, out string? value)
            ? value
            : string.IsNullOrWhiteSpace(id)
                ? "unassigned"
                : id.Replace('_', ' ');

    private static IReadOnlyList<string> BuildFactionSignals(BlackLedgerFactionDocument faction)
        => (faction.Stats ?? new Dictionary<string, int>())
            .OrderByDescending(static pair => pair.Value)
            .Take(3)
            .Select(static pair => $"{ResolvePublicMetricLabel(pair.Key)} {pair.Value}")
            .ToArray();

    private static string ResolvePublicMetricLabel(string metric)
        => metric switch
        {
            "license_polish" => "permit leverage",
            "proof_trail_strength" => "signal discipline",
            "mysad_density" => "mystic density",
            "vehicle_package_demand" => "vehicle demand",
            "closeout_witnesses" => "street witnesses",
            _ => metric.Replace('_', ' '),
        };

    private static string BuildDistrictSummary(BlackLedgerDistrictDocument district)
        => $"{district.Name} is led by {GetDominantFactionId(district).Replace('_', ' ')} with influence {district.Influence} and heat {district.Heat}.";

    private static (string primary, string secondary, string icon) ResolveFactionVisual(string factionId)
        => NormalizeSlug(factionId) switch
        {
            "glass-tower-compact" => ("#5ce2ff", "#89a7ff", "grid"),
            "rust-market-syndicate" => ("#ff8a3d", "#ff5d73", "credit-chip-broken"),
            "ashline-circle" => ("#9c6cff", "#ffb84d", "ritual-eye"),
            "neon-docks-union" => ("#63f2b6", "#5ce2ff", "cargo-node"),
            "ghostline-network" => ("#a9b8cf", "#5ce2ff", "signal-mask"),
            "barrens-free-wardens" => ("#ffb84d", "#63f2b6", "ward-shield"),
            _ => ("#5ce2ff", "#a9b8cf", "signal-node"),
        };

    private static (int x, int y) ComputePolygonCenter(List<List<int>>? polygon)
    {
        if (polygon is null || polygon.Count == 0)
        {
            return (0, 0);
        }

        int count = 0;
        int x = 0;
        int y = 0;
        foreach (List<int> point in polygon)
        {
            if (point.Count < 2)
            {
                continue;
            }

            x += point[0];
            y += point[1];
            count++;
        }

        return count == 0 ? (0, 0) : (x / count, y / count);
    }

    private static int ComputeDistrictConfidence(BlackLedgerDistrictDocument district)
        => Math.Clamp(100 - Math.Abs(district.Heat - district.Influence), 38, 91);

    private static int ComputeDistrictVolatility(BlackLedgerDistrictDocument district)
        => Math.Clamp(Math.Abs(district.Heat - district.Influence) + 18, 21, 94);

    private static string ComputeDistrictTrend(BlackLedgerDistrictDocument district)
        => district.Heat >= 70 ? "rising" : district.Influence <= 45 ? "volatile" : "stable";

    private static int ComputeDistrictDelta(BlackLedgerDistrictDocument district)
        => NormalizeSlug(GetDistrictId(district)) switch
        {
            "rust-bazaar" => 8,
            "ashline-ward" => 5,
            "neon-docks" => 4,
            "ghostline-east" => 6,
            "free-ward" => 3,
            "transit-spine" => 2,
            "old-signal-loop" => 6,
            _ => 0,
        };

    private static string NormalizeMode(string currentMode)
        => currentMode.Trim().ToLowerInvariant() switch
        {
            "conflict" => "conflict",
            "intel" => "intel",
            "economy" => "economy",
            "magic" => "magic",
            "matrix" => "matrix",
            "recent-changes" => "recent-changes",
            _ => "influence",
        };

    private static IReadOnlyList<BlackLedgerMapModeViewModel> BuildMapModes(string currentMode)
        => [
            new("influence", "Influence", "Faction control, confidence, and contested zones.", currentMode == "influence"),
            new("conflict", "Conflict", "Heat spikes, suppression, and pressure fronts.", currentMode == "conflict"),
            new("intel", "Intel", "What the public-safe receipts can actually support.", currentMode == "intel"),
            new("economy", "Economy", "Debt, logistics, and package pressure lanes.", currentMode == "economy"),
            new("magic", "Magic", "Awakened pressure and ritual fallout.", currentMode == "magic"),
            new("matrix", "Matrix", "Signal routing, rumor suppression, and data pressure.", currentMode == "matrix"),
            new("recent-changes", "Recent changes", "Turn replay and the latest visible delta.", currentMode == "recent-changes"),
        ];

    private IReadOnlyList<BlackLedgerMapEventViewModel> BuildMapEvents(BlackLedgerWorldPreviewViewModel world)
    {
        BlackLedgerWorldSeedDocument? seed = TryLoadSeed();
        if (seed is not null && GetEventDocuments(seed).Count > 0)
        {
            var regionById = world.Districts.ToDictionary(static item => item.Id, StringComparer.OrdinalIgnoreCase);
            var dispatchesById = ListDispatches(world.CurrentTurn).ToDictionary(static item => item.DispatchId, StringComparer.OrdinalIgnoreCase);
            var seededEvents = GetEventDocuments(seed)
                .Where(item => item.Turn == world.CurrentTurn)
                .Select(item =>
                {
                    regionById.TryGetValue(item.RegionId, out BlackLedgerDistrictViewModel? region);
                    return new BlackLedgerMapEventViewModel(
                        item.EventId,
                        item.EventType,
                        region?.Id ?? item.RegionId,
                        $"{region?.Name ?? item.RegionId} — {item.PublicSummary}",
                        item.PublicSummary,
                        item.Severity,
                        item.Confidence,
                        item.Status,
                        region?.CenterX ?? 0,
                        region?.CenterY ?? 0,
                        item.Turn == world.CurrentTurn,
                        item.SourceReceiptId,
                        "/ledger/turns/1",
                        !string.IsNullOrWhiteSpace(item.DispatchId) && dispatchesById.TryGetValue(item.DispatchId, out var dispatch) ? dispatch.Href : null);
                })
                .ToArray();
            if (seededEvents.Length > 0)
            {
                return seededEvents;
            }
        }

        BlackLedgerTickReceiptViewModel tick = world.LastTick ?? throw new InvalidOperationException("World preview is missing the last tick.");
        var regionByName = world.Districts.ToDictionary(static item => item.Name, StringComparer.OrdinalIgnoreCase);
        var dispatches = ListDispatches(world.CurrentTurn).ToDictionary(static item => item.DispatchId, StringComparer.OrdinalIgnoreCase);
        var events = new List<BlackLedgerMapEventViewModel>();

        foreach (BlackLedgerTickEffectViewModel effect in tick.Effects)
        {
            BlackLedgerDistrictViewModel region = ResolveEventRegion(effect, world);
            string eventType = ResolveEventType(effect);
            string? dispatchHref = dispatches.Values.FirstOrDefault(dispatch =>
                dispatch.InvolvedDistricts.Any(district => regionByName.ContainsKey(district) && string.Equals(district, region.Name, StringComparison.OrdinalIgnoreCase))
                || dispatch.InvolvedFactions.Any(faction => effect.Target.Contains(faction, StringComparison.OrdinalIgnoreCase)))?.Href;
            events.Add(new BlackLedgerMapEventViewModel(
                EventId: $"event-{NormalizeSlug(effect.Target)}-{NormalizeSlug(effect.Metric)}",
                EventType: eventType,
                RegionId: region.Id,
                Title: $"{effect.Target} — {effect.Metric}",
                Summary: effect.PublicReason,
                Severity: Math.Clamp(Math.Abs(effect.Delta) * 10 + region.Heat / 2, 24, 96),
                Confidence: region.Confidence,
                Status: effect.Delta >= 0 ? "active" : "suppressed",
                X: region.CenterX,
                Y: region.CenterY,
                NewThisTurn: true,
                SourceReceiptId: tick.ReceiptId,
                SourceReceiptHref: "/ledger/closeouts",
                DispatchHref: dispatchHref));
        }

        return events;
    }

    private IReadOnlyList<BlackLedgerMapArcViewModel> BuildMapArcs(BlackLedgerWorldPreviewViewModel world)
    {
        BlackLedgerWorldSeedDocument? seed = LoadSeedDocument();
        if (seed is not null && GetArcDocuments(seed).Count > 0)
        {
            var seededArcs = GetArcDocuments(seed)
                .Where(item => item.Turn == world.CurrentTurn)
                .Select(item => new BlackLedgerMapArcViewModel(
                    item.ArcId,
                    item.SourceRegionId,
                    item.TargetRegionId,
                    item.ArcType,
                    item.Intensity,
                    item.Direction,
                    $"{item.ArcType} pressure from {item.SourceRegionId} to {item.TargetRegionId}."))
                .ToArray();
            if (seededArcs.Length > 0)
            {
                return seededArcs;
            }
        }

        var arcs = new List<BlackLedgerMapArcViewModel>();
        void Add(string id, string source, string target, string type, int intensity, string summary)
            => arcs.Add(new BlackLedgerMapArcViewModel(id, source, target, type, intensity, "forward", summary));

        Add("arc-rust-transit", "rust-bazaar", "transit-spine", "debt", 88, "Rust Bazaar debt heat spills into the contested transit lane.");
        Add("arc-ashline-signal", "ashline-ward", "old-signal-loop", "magic", 74, "Ashline source clarity disputes bleed into the old signal corridor.");
        Add("arc-neon-transit", "neon-docks", "transit-spine", "logistics", 67, "Cargo and drone pressure route through the central spine.");
        Add("arc-ghost-neon", "ghostline-east", "neon-docks", "intel", 63, "Ghostline suppression keeps the dock rumor lane bounded.");
        Add("arc-free-rust", "free-ward", "rust-bazaar", "conflict", 58, "Street attrition and debt collections share the same pressure edge.");

        return arcs;
    }

    private static IReadOnlyList<BlackLedgerMapReplayStepViewModel> BuildReplaySteps(
        BlackLedgerWorldPreviewViewModel world,
        BlackLedgerWorldSeedDocument? seed)
        => world.TurnNavigation
            .Select(turn =>
            {
                BlackLedgerTurnDocument? turnDocument = seed?.Turns?.FirstOrDefault(item => item.Turn == turn.Turn);
                string summary = turn.Current && world.LastTick is not null
                    ? world.LastTick.Summary
                    : !string.IsNullOrWhiteSpace(turnDocument?.Summary)
                        ? turnDocument.Summary
                        : $"Replay Turn {turn.Turn}.";
                if (turnDocument?.ActionBeats?.Count > 0)
                {
                    int playerCount = turnDocument.ActionBeats.Count(static beat => string.Equals(beat.ActorKind, "player", StringComparison.OrdinalIgnoreCase));
                    int gmCount = turnDocument.ActionBeats.Count(static beat => string.Equals(beat.ActorKind, "gm", StringComparison.OrdinalIgnoreCase));
                    summary = $"{summary} {turnDocument.ActionBeats.Count} visible beats seeded: {playerCount} player, {gmCount} GM.";
                }

                return new BlackLedgerMapReplayStepViewModel(
                    turn.Turn,
                    turn.Label,
                    summary,
                    turn.Current);
            })
            .ToArray();

    private static BlackLedgerDistrictViewModel ResolveEventRegion(BlackLedgerTickEffectViewModel effect, BlackLedgerWorldPreviewViewModel world)
    {
        string target = effect.Target.ToLowerInvariant();
        return world.Districts.FirstOrDefault(district =>
                   target.Contains(district.Name.ToLowerInvariant(), StringComparison.Ordinal)
                   || target.Contains(district.DominantFaction.ToLowerInvariant(), StringComparison.Ordinal))
               ?? (target.Contains("rust", StringComparison.Ordinal) ? world.Districts.First(d => d.Id == "rust-bazaar")
                   : target.Contains("ashline", StringComparison.Ordinal) ? world.Districts.First(d => d.Id == "ashline-ward")
                   : target.Contains("neon", StringComparison.Ordinal) ? world.Districts.First(d => d.Id == "neon-docks")
                   : target.Contains("ghost", StringComparison.Ordinal) ? world.Districts.First(d => d.Id == "ghostline-east")
                   : target.Contains("barrens", StringComparison.Ordinal) ? world.Districts.First(d => d.Id == "free-ward")
                   : world.Districts.First(d => d.Id == "transit-spine"));
    }

    private static string ResolveEventType(BlackLedgerTickEffectViewModel effect)
    {
        string target = effect.Target.ToLowerInvariant();
        string metric = effect.Metric.ToLowerInvariant();
        if (target.Contains("ghost", StringComparison.Ordinal) || metric.Contains("signal", StringComparison.Ordinal))
        {
            return "intel";
        }

        if (target.Contains("ashline", StringComparison.Ordinal) || metric.Contains("mysad", StringComparison.Ordinal) || metric.Contains("drain", StringComparison.Ordinal))
        {
            return "magic";
        }

        if (target.Contains("neon", StringComparison.Ordinal) || metric.Contains("vehicle", StringComparison.Ordinal) || metric.Contains("drone", StringComparison.Ordinal))
        {
            return "logistics";
        }

        if (metric.Contains("debt", StringComparison.Ordinal) || metric.Contains("favor", StringComparison.Ordinal))
        {
            return "debt";
        }

        return "conflict";
    }

    private static bool IsWorldPublicSafe(BlackLedgerWorldSeedDocument world)
    {
        if ((!string.Equals(world.Status, "preseeded_preview", StringComparison.Ordinal)
                && !string.Equals(world.Status, "seeded_preview", StringComparison.Ordinal)
                && !string.Equals(world.Status, "flagship_seeded", StringComparison.Ordinal))
            || world.OfficialIpNamesPresent
            || world.SourcebookTextPresent
            || world.OfficialMapsPresent
            || world.OfficialLogosPresent
            || world.PrivateCampaignDataPresent
            || !world.PublicProjectionAllowed
            || !string.Equals(world.LoreMode, "public_seed", StringComparison.Ordinal)
            || GetDistrictDocuments(world).Count < 8
            || GetFactionDocuments(world).Count < 6)
        {
            return false;
        }

        var aiIds = GetAiPersonalities(world)
            .Select(static personality => GetPersonalityId(personality))
            .Where(static id => !string.IsNullOrWhiteSpace(id))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        if ((world.Turns ?? []).All(static turn => turn.Turn != 1 || string.IsNullOrWhiteSpace(turn.ReceiptId)))
        {
            return false;
        }

        return GetFactionDocuments(world).All(faction =>
            faction.ManagementPosts is not null
            && aiIds.Contains(faction.ManagementPosts.FactionLeader)
            && aiIds.Contains(faction.ManagementPosts.FieldGm)
            && aiIds.Contains(faction.ManagementPosts.IntelProvider));
    }

    private static BlackLedgerPublicStatViewModel CreatePublicStat(
        string id,
        string title,
        string value,
        string period,
        string sampleSize,
        int sampleCount,
        string confidenceKey,
        string confidence,
        string privacyNote,
        string sourceKind,
        string sourceLabel,
        string sourceSummary,
        string status,
        string href)
        => new(
            Id: id,
            Title: title,
            Value: value,
            Scope: "Public aggregate",
            ScopeKey: "public_aggregate",
            Period: period,
            SampleSize: sampleSize,
            SampleCount: sampleCount,
            Confidence: confidence,
            ConfidenceKey: confidenceKey,
            PrivacyNote: privacyNote,
            Source: sourceKind,
            SourceDetail: new BlackLedgerPublicStatSourceViewModel(
                Kind: sourceKind,
                Label: sourceLabel,
                ProvenanceSummary: sourceSummary,
                PreviewOnly: !string.Equals(status, "live", StringComparison.Ordinal),
                PublicSafe: true),
            Status: status,
            Href: href);

    private static bool IsPublicSafe(BlackLedgerPublicStatViewModel stat, int minimumLiveSampleSize)
        => !string.IsNullOrWhiteSpace(stat.Id)
           && !string.IsNullOrWhiteSpace(stat.Title)
           && !string.IsNullOrWhiteSpace(stat.Value)
           && string.Equals(stat.Scope, "Public aggregate", StringComparison.Ordinal)
           && string.Equals(stat.ScopeKey, "public_aggregate", StringComparison.Ordinal)
           && !string.IsNullOrWhiteSpace(stat.Period)
           && !string.IsNullOrWhiteSpace(stat.SampleSize)
           && stat.SampleCount >= 0
           && !string.IsNullOrWhiteSpace(stat.Confidence)
           && !string.IsNullOrWhiteSpace(stat.ConfidenceKey)
           && !string.IsNullOrWhiteSpace(stat.PrivacyNote)
           && !string.IsNullOrWhiteSpace(stat.Source)
           && stat.SourceDetail is not null
           && stat.SourceDetail.PublicSafe
           && !string.IsNullOrWhiteSpace(stat.Status)
           && !string.IsNullOrWhiteSpace(stat.Href)
           && (!string.Equals(stat.Status, "live", StringComparison.Ordinal) || stat.SampleCount >= minimumLiveSampleSize)
           && !ContainsForbiddenPublicTerms(stat.Title)
           && !ContainsForbiddenPublicTerms(stat.Value)
           && !ContainsForbiddenPublicTerms(stat.PrivacyNote)
           && !ContainsForbiddenPublicTerms(stat.Source)
           && !ContainsForbiddenPublicTerms(stat.SourceDetail.Label)
           && !ContainsForbiddenPublicTerms(stat.SourceDetail.ProvenanceSummary);

    private static bool ContainsForbiddenPublicTerms(string value)
        => ForbiddenPublicTerms.Any(term => value.Contains(term, StringComparison.OrdinalIgnoreCase));

    private static string ComputeHash(string value)
        => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));

    private static IReadOnlyList<BlackLedgerDistrictDocument> GetDistrictDocuments(BlackLedgerWorldSeedDocument seed)
        => seed.Districts?.Count > 0 ? seed.Districts : seed.Map?.Districts ?? [];

    private static IReadOnlyList<BlackLedgerFactionDocument> GetFactionDocuments(BlackLedgerWorldSeedDocument seed)
        => seed.Factions ?? [];

    private static IReadOnlyList<BlackLedgerAiPersonalityDocument> GetAiPersonalities(BlackLedgerWorldSeedDocument seed)
        => seed.AiPersonalities ?? [];

    private static IReadOnlyList<BlackLedgerWorldEventDocument> GetEventDocuments(BlackLedgerWorldSeedDocument seed)
        => seed.Events ?? [];

    private static IReadOnlyList<BlackLedgerWorldArcDocument> GetArcDocuments(BlackLedgerWorldSeedDocument seed)
        => seed.Arcs ?? [];

    private static IReadOnlyList<BlackLedgerPackagePressureDocument> GetPackagePressureDocuments(BlackLedgerWorldSeedDocument seed, BlackLedgerTurnDocument? turn)
    {
        if (turn?.PackagePressureIds?.Count > 0)
        {
            return (seed.PackagePressure ?? [])
                .Where(item => turn.PackagePressureIds.Contains(item.PackageId, StringComparer.OrdinalIgnoreCase))
                .ToArray();
        }

        return seed.PackagePressure ?? turn?.PackagePressure ?? [];
    }

    private static IReadOnlyList<BlackLedgerDispatchDocument> GetDispatchDocuments(BlackLedgerWorldSeedDocument seed, int? requestedTurn = null)
    {
        IEnumerable<BlackLedgerDispatchDocument> dispatches = seed.Dispatches ?? [];
        if (requestedTurn.HasValue)
        {
            dispatches = dispatches.Where(item => item.Turn == requestedTurn.Value);
        }

        return dispatches.ToArray();
    }

    private static string GetPersonalityId(BlackLedgerAiPersonalityDocument personality)
        => string.IsNullOrWhiteSpace(personality.PersonalityId) ? personality.Id : personality.PersonalityId;

    private static string GetPersonalityLabel(BlackLedgerAiPersonalityDocument personality)
        => string.IsNullOrWhiteSpace(personality.PublicLabel)
            ? GetPersonalityId(personality).Replace('_', ' ')
            : personality.PublicLabel;

    private static string GetDistrictId(BlackLedgerDistrictDocument district)
        => string.IsNullOrWhiteSpace(district.Id) ? district.RegionId : district.Id;

    private static string GetDominantFactionId(BlackLedgerDistrictDocument district)
        => string.IsNullOrWhiteSpace(district.DominantFaction) ? district.DominantFactionId : district.DominantFaction;

    private static string GetFactionId(BlackLedgerFactionDocument faction)
        => string.IsNullOrWhiteSpace(faction.Id) ? faction.FactionId : faction.Id;

    private static IReadOnlyList<string> ResolveDispatchFactions(BlackLedgerDispatchDocument dispatch)
    {
        string text = $"{dispatch.DispatchId} {dispatch.Title}".ToLowerInvariant();
        List<string> factions = [];
        if (text.Contains("glass"))
        {
            factions.Add("Glass Tower Compact");
        }
        if (text.Contains("rust"))
        {
            factions.Add("Rust Market Syndicate");
        }
        if (text.Contains("ashline"))
        {
            factions.Add("Ashline Circle");
        }
        if (text.Contains("neon"))
        {
            factions.Add("Neon Docks Union");
        }
        if (text.Contains("ghostline"))
        {
            factions.Add("Ghostline Network");
        }
        if (text.Contains("free_wardens") || text.Contains("free ward"))
        {
            factions.Add("Barrens Free Wardens");
        }

        return factions.Count == 0 ? ["Emerald Sprawl"] : factions;
    }

    private static IReadOnlyList<string> ResolveDispatchDistricts(BlackLedgerDispatchDocument dispatch)
    {
        string text = $"{dispatch.DispatchId} {dispatch.Title}".ToLowerInvariant();
        List<string> districts = [];
        if (text.Contains("glass"))
        {
            districts.Add("Glass Heights");
        }
        if (text.Contains("rust"))
        {
            districts.Add("Rust Bazaar");
        }
        if (text.Contains("ashline"))
        {
            districts.Add("Ashline Ward");
        }
        if (text.Contains("neon"))
        {
            districts.Add("Neon Docks");
        }
        if (text.Contains("ghostline"))
        {
            districts.Add("Ghostline East");
        }
        if (text.Contains("free_wardens") || text.Contains("free ward"))
        {
            districts.Add("Free Ward");
        }

        return districts;
    }

    private static IReadOnlyList<string> ResolveDispatchPackageLinks(BlackLedgerDispatchDocument dispatch)
    {
        string body = dispatch.BodyMarkdown.ToLowerInvariant();
        List<string> links = [];
        if (body.Contains("package"))
        {
            links.Add("/packages");
        }
        if (body.Contains("awakened"))
        {
            links.Add("/packages/awakened-build-explainers");
        }
        if (body.Contains("drone"))
        {
            links.Add("/packages/drone-logistics-overlay");
        }
        if (body.Contains("debt"))
        {
            links.Add("/packages/debt-ledger-visibility");
        }

        return links.Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
    }

    private sealed record SelectedTurnContext(
        BlackLedgerTurnDocument? Turn,
        bool IsDeterministicPreview,
        string Mode,
        string? CreatedAtUtc);

    public sealed class BlackLedgerWorldSeedDocument
    {
        public string SchemaVersion { get; set; } = string.Empty;
        public string WorldId { get; set; } = string.Empty;
        public string PublicName { get; set; } = string.Empty;
        public string PublicSubtitle { get; set; } = string.Empty;
        public string Status { get; set; } = string.Empty;
        public string Source { get; set; } = string.Empty;
        public string LoreMode { get; set; } = string.Empty;
        public bool PublicProjectionAllowed { get; set; }
        public bool OfficialIpNamesPresent { get; set; }
        public bool SourcebookTextPresent { get; set; }
        public bool OfficialMapsPresent { get; set; }
        public bool OfficialLogosPresent { get; set; }
        public bool PrivateCampaignDataPresent { get; set; }
        public int CurrentTurn { get; set; }
        public BlackLedgerSourcePolicyDocument? SourcePolicy { get; set; }
        public BlackLedgerPublicUiNoisePolicyDocument? PublicUiNoisePolicy { get; set; }
        public BlackLedgerPublicSafetyDocument? PublicSafety { get; set; }
        public BlackLedgerMapDocument? Map { get; set; }
        public List<BlackLedgerDistrictDocument>? Districts { get; set; }
        public List<BlackLedgerFactionDocument>? Factions { get; set; }
        public List<BlackLedgerAiPersonalityDocument>? AiPersonalities { get; set; }
        public List<BlackLedgerGlobalPostDocument>? GlobalPosts { get; set; }
        public BlackLedgerStewardshipTransferDocument? StewardshipTransferPreview { get; set; }
        public List<BlackLedgerWorldEventDocument>? Events { get; set; }
        public List<BlackLedgerWorldArcDocument>? Arcs { get; set; }
        public List<BlackLedgerPackagePressureDocument>? PackagePressure { get; set; }
        public List<BlackLedgerTurnDocument>? Turns { get; set; }
        public List<BlackLedgerDispatchDocument>? Dispatches { get; set; }
        public List<BlackLedgerDeterministicTickDocument>? DeterministicTestTicks { get; set; }
    }

    public sealed class BlackLedgerSourcePolicyDocument
    {
        public bool OfficialShadowrunNamesAllowedOnPublicRoutes { get; set; }
        public bool OfficialMegacorpNamesAllowedOnPublicRoutes { get; set; }
        public bool OfficialLogosAllowed { get; set; }
        public bool OfficialMapsAllowed { get; set; }
        public bool SourcebookTextAllowed { get; set; }
        public bool CanonEventsAllowed { get; set; }
        public bool PrivateCampaignLoreLabelsAllowedOnPublicRoutes { get; set; }
        public bool LicensedCanonPackEnabled { get; set; }
        public bool LicenseReceiptRequiredForOfficialLore { get; set; }
        public string PublicCopyNote { get; set; } = string.Empty;
    }

    public sealed class BlackLedgerPublicUiNoisePolicyDocument
    {
        public bool NoDeadLinks { get; set; }
        public bool NoPlaceholderButtons { get; set; }
        public bool NoHrefHashPlaceholders { get; set; }
        public bool NoJavascriptVoidLinks { get; set; }
        public int MaxPrimaryCtasPerSurface { get; set; }
        public int MaxTotalCtasHomepageLedgerTeaser { get; set; }
        public int MaxMapTeaserStats { get; set; }
        public int MaxMapTeaserHotspots { get; set; }
        public bool ProofLinksOnlyInStatusOrReceipts { get; set; }
        public bool ArtifactShelfNotOnHomepage { get; set; }
    }

    public sealed class BlackLedgerPublicSafetyDocument
    {
        public bool OfficialLore { get; set; }
        public bool UsesSourcebookText { get; set; }
        public bool UsesPrivateUserData { get; set; }
        public string PublicStatsScope { get; set; } = string.Empty;
        public bool RealUserIdentificationAllowed { get; set; }
        public int MinSampleSizeForLivePublicStats { get; set; }
    }

    public sealed class BlackLedgerMapDocument
    {
        public List<BlackLedgerDistrictDocument>? Districts { get; set; }
    }

    public sealed class BlackLedgerDistrictDocument
    {
        public string RegionId { get; set; } = string.Empty;
        public string Id { get; set; } = string.Empty;
        public string Name { get; set; } = string.Empty;
        public string Summary { get; set; } = string.Empty;
        public List<List<int>>? Polygon { get; set; }
        public string DominantFactionId { get; set; } = string.Empty;
        public string DominantFaction { get; set; } = string.Empty;
        public int Influence { get; set; }
        public int Heat { get; set; }
        public int Confidence { get; set; }
        public int Volatility { get; set; }
        public string Trend { get; set; } = string.Empty;
        public int DeltaSinceLastTick { get; set; }
        public string LatestDispatchId { get; set; } = string.Empty;
    }

    public sealed class BlackLedgerFactionDocument
    {
        public string FactionId { get; set; } = string.Empty;
        public string Id { get; set; } = string.Empty;
        public string PublicName { get; set; } = string.Empty;
        public string ShortName { get; set; } = string.Empty;
        public string Archetype { get; set; } = string.Empty;
        public string PublicSummary { get; set; } = string.Empty;
        public string PublicRole { get; set; } = string.Empty;
        public string Tone { get; set; } = string.Empty;
        public string ColorPrimary { get; set; } = string.Empty;
        public string ColorSecondary { get; set; } = string.Empty;
        public string Icon { get; set; } = string.Empty;
        public string Type { get; set; } = string.Empty;
        public BlackLedgerManagementPostsDocument? ManagementPosts { get; set; }
        public Dictionary<string, int>? Stats { get; set; }
    }

    public sealed class BlackLedgerManagementPostsDocument
    {
        public string FactionLeader { get; set; } = string.Empty;
        public string FieldGm { get; set; } = string.Empty;
        public string IntelProvider { get; set; } = string.Empty;
    }

    public sealed class BlackLedgerAiPersonalityDocument
    {
        public string PersonalityId { get; set; } = string.Empty;
        public string Id { get; set; } = string.Empty;
        public string PublicLabel { get; set; } = string.Empty;
        public string Role { get; set; } = string.Empty;
        public string? Authority { get; set; }
        public string? FactionId { get; set; }
        public string? Faction { get; set; }
        public string? Tone { get; set; }
        public List<string>? Goals { get; set; }
        public string? RiskAppetite { get; set; }
    }

    public sealed class BlackLedgerGlobalPostDocument
    {
        public string Id { get; set; } = string.Empty;
        public string HolderType { get; set; } = string.Empty;
        public string? FallbackPersonality { get; set; }
        public string PublicLabel { get; set; } = string.Empty;
        public string PublicSummary { get; set; } = string.Empty;
    }

    public sealed class BlackLedgerStewardshipTransferDocument
    {
        public string ReceiptType { get; set; } = string.Empty;
        public string PostId { get; set; } = string.Empty;
        public string OldHolder { get; set; } = string.Empty;
        public string NewHolder { get; set; } = string.Empty;
        public string NewHolderType { get; set; } = string.Empty;
        public string OccurredAt { get; set; } = string.Empty;
        public string Reason { get; set; } = string.Empty;
        public string OperatorId { get; set; } = string.Empty;
        public string PublicVisibility { get; set; } = string.Empty;
    }

    public sealed class BlackLedgerTurnDocument
    {
        public int Turn { get; set; }
        public string TurnId { get; set; } = string.Empty;
        public string State { get; set; } = string.Empty;
        public string Headline { get; set; } = string.Empty;
        public string Summary { get; set; } = string.Empty;
        public string? ReceiptId { get; set; }
        public List<BlackLedgerTurnEffectDocument>? Effects { get; set; }
        public List<string>? EventIds { get; set; }
        public List<string>? ArcIds { get; set; }
        public List<string>? PackagePressureIds { get; set; }
        public bool PublicSafe { get; set; }
        public BlackLedgerTurnPrivacyResultDocument? PrivacyResult { get; set; }
        public BlackLedgerTurnIpResultDocument? IpResult { get; set; }
        public string InputStateHash { get; set; } = string.Empty;
        public string DecisionPacketHash { get; set; } = string.Empty;
        public string OutputStateHash { get; set; } = string.Empty;
        public List<BlackLedgerActionBeatDocument>? ActionBeats { get; set; }
        public List<BlackLedgerPackagePressureDocument>? PackagePressure { get; set; }
    }

    public sealed class BlackLedgerTurnPrivacyResultDocument
    {
        public string Status { get; set; } = string.Empty;
        public List<string>? BlockedFields { get; set; }
    }

    public sealed class BlackLedgerTurnIpResultDocument
    {
        public string Status { get; set; } = string.Empty;
        public bool OfficialIpNamesPresent { get; set; }
        public bool SourcebookTextPresent { get; set; }
    }

    public sealed class BlackLedgerDeterministicTickDocument
    {
        public int Turn { get; set; }
        public string SeedId { get; set; } = string.Empty;
        public string Mode { get; set; } = string.Empty;
        public string State { get; set; } = string.Empty;
        public string Summary { get; set; } = string.Empty;
        public string ReceiptId { get; set; } = string.Empty;
        public string CreatedAtUtc { get; set; } = string.Empty;
        public List<BlackLedgerTurnEffectDocument>? Effects { get; set; }
        public List<BlackLedgerPackagePressureDocument>? PackagePressure { get; set; }
    }

    public sealed class BlackLedgerTurnEffectDocument
    {
        public string Target { get; set; } = string.Empty;
        public string Metric { get; set; } = string.Empty;
        public int Delta { get; set; }
        public string PublicReason { get; set; } = string.Empty;
    }

    public sealed class BlackLedgerActionBeatDocument
    {
        public string BeatId { get; set; } = string.Empty;
        public string ActorKind { get; set; } = string.Empty;
        public string ActorLabel { get; set; } = string.Empty;
        public string BeatLabel { get; set; } = string.Empty;
        public string ActionSummary { get; set; } = string.Empty;
        public string Stakes { get; set; } = string.Empty;
        public string ProofNote { get; set; } = string.Empty;
        public string VisualHook { get; set; } = string.Empty;
        public string CommandIntent { get; set; } = string.Empty;
        public string ConsequenceLine { get; set; } = string.Empty;
    }

    public sealed class BlackLedgerPackagePressureDocument
    {
        public string PackageId { get; set; } = string.Empty;
        public string PublicName { get; set; } = string.Empty;
        public int Pressure { get; set; }
        public string Status { get; set; } = string.Empty;
        public List<string>? SourceEventIds { get; set; }
        public string PublicSummary { get; set; } = string.Empty;
        public string Route { get; set; } = string.Empty;
    }

    public sealed class BlackLedgerWorldEventDocument
    {
        public string EventId { get; set; } = string.Empty;
        public int Turn { get; set; }
        public string EventType { get; set; } = string.Empty;
        public string RegionId { get; set; } = string.Empty;
        public List<string>? FactionIds { get; set; }
        public int Severity { get; set; }
        public int Confidence { get; set; }
        public string Status { get; set; } = string.Empty;
        public string SourceReceiptId { get; set; } = string.Empty;
        public string DispatchId { get; set; } = string.Empty;
        public string PublicSummary { get; set; } = string.Empty;
        public string Animation { get; set; } = string.Empty;
    }

    public sealed class BlackLedgerWorldArcDocument
    {
        public string ArcId { get; set; } = string.Empty;
        public int Turn { get; set; }
        public string SourceRegionId { get; set; } = string.Empty;
        public string TargetRegionId { get; set; } = string.Empty;
        public string ArcType { get; set; } = string.Empty;
        public int Intensity { get; set; }
        public string Direction { get; set; } = string.Empty;
        public string SourceReceiptId { get; set; } = string.Empty;
    }

    public sealed class BlackLedgerDispatchDocument
    {
        public string DispatchId { get; set; } = string.Empty;
        public string WorldId { get; set; } = string.Empty;
        public int Turn { get; set; }
        public string DispatchType { get; set; } = string.Empty;
        public List<string>? SourceReceiptIds { get; set; }
        public string Title { get; set; } = string.Empty;
        public string Summary { get; set; } = string.Empty;
        public string BodyMarkdown { get; set; } = string.Empty;
        public string PrivacyStatus { get; set; } = string.Empty;
        public string IpStatus { get; set; } = string.Empty;
        public string FactConsistencyStatus { get; set; } = string.Empty;
        public bool PublicProjectionAllowed { get; set; }
        public bool OfficialIpNamesPresent { get; set; }
        public bool SourcebookTextPresent { get; set; }
    }
}

public sealed record BlackLedgerMapApiDocument(
    string WorldId,
    string DisplayName,
    int CurrentTurn,
    string Projection,
    string CurrentMode,
    string SafetyNote,
    string MapNote,
    IReadOnlyList<BlackLedgerMapRegionApiDocument> Regions,
    IReadOnlyList<BlackLedgerMapFactionApiDocument> Factions,
    IReadOnlyList<BlackLedgerMapEventApiDocument> Events,
    IReadOnlyList<BlackLedgerMapArcApiDocument> Arcs,
    IReadOnlyList<BlackLedgerMapModeViewModel> Modes,
    IReadOnlyList<BlackLedgerMapReplayStepViewModel> ReplaySteps,
    BlackLedgerTickReceiptViewModel LatestTick);

public sealed record BlackLedgerMapRegionApiDocument(
    string RegionId,
    string Name,
    string PolygonPoints,
    string DominantFactionId,
    int Influence,
    int Heat,
    int Confidence,
    int Volatility,
    string Trend,
    int DeltaSinceLastTick,
    int CenterX,
    int CenterY,
    string Summary);

public sealed record BlackLedgerMapFactionApiDocument(
    string FactionId,
    string Name,
    string PublicSummary,
    string ColorPrimary,
    string ColorSecondary,
    string Icon,
    string Type);

public sealed record BlackLedgerMapEventApiDocument(
    string EventId,
    string EventType,
    string RegionId,
    int Severity,
    int Confidence,
    string Status,
    int Turn,
    string SourceReceiptId,
    string? DispatchHref,
    string Title,
    string Summary,
    int X,
    int Y,
    bool NewThisTurn);

public sealed record BlackLedgerMapArcApiDocument(
    string ArcId,
    string SourceRegionId,
    string TargetRegionId,
    string ArcType,
    int Intensity,
    string Direction,
    string Summary);

public sealed record BlackLedgerRegionDeltaApiDocument(
    string RegionId,
    string Name,
    int DeltaSinceLastTick,
    string Trend,
    int Heat,
    int Influence);

public sealed record BlackLedgerTickDeltaApiDocument(
    string WorldId,
    int FromTurn,
    int ToTurn,
    string Summary,
    IReadOnlyList<BlackLedgerRegionDeltaApiDocument> RegionDeltas,
    IReadOnlyList<string> EventIds,
    IReadOnlyList<string> ArcIds,
    IReadOnlyList<string> DispatchIds);
