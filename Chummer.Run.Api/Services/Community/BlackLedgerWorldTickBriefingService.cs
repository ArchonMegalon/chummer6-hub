using Chummer.Run.Api.ViewModels;
using System.Globalization;

namespace Chummer.Run.Api.Services.Community;

public sealed class BlackLedgerWorldTickBriefingService
{
    private readonly BlackLedgerPublicStatsService _stats;
    private readonly BlackLedgerFactionOnboardingService _factions;

    public BlackLedgerWorldTickBriefingService(
        BlackLedgerPublicStatsService stats,
        BlackLedgerFactionOnboardingService factions)
    {
        _stats = stats;
        _factions = factions;
    }

    public BlackLedgerWorldTurnBriefingViewModel? BuildWorldTurnBriefing(int? requestedTurn, string ledgerBasePath = "/ledger")
    {
        BlackLedgerWorldPreviewViewModel? world = _stats.LoadWorldPreview(requestedTurn);
        BlackLedgerPublicStatsService.BlackLedgerWorldSeedDocument? seed = _stats.LoadSeedDocument();
        BlackLedgerTickReceiptViewModel? tick = world?.LastTick;
        if (world is null || tick is null)
        {
            return null;
        }

        int fromTurn = Math.Max(0, tick.Turn - 1);
        string transitionLabel = $"Turn {fromTurn} -> Turn {tick.Turn}";
        string transitionNarrative = fromTurn == 0
            ? "Turn 0 was operator setup, hidden clocks, and seeded faction posture. Turn 1 is the first public city reaction that players can inspect without touching private table state."
            : $"Turn {fromTurn} carried forward the prior public board state. Turn {tick.Turn} is the receipt-backed city answer to those visible pressures.";
        string stateSummary = BuildStateSummary(world);
        string inboxHeadline = fromTurn == 0
            ? $"World Turn 1 opened the board for {world.PublicName}"
            : $"World Turn {tick.Turn} changed the pressure picture for {world.PublicName}";
        string newsreelLead = $"{transitionNarrative} {tick.Summary}";
        string validationJsonHref = $"{ledgerBasePath.TrimEnd('/')}/turns/{tick.Turn}/newsreel.json";
        IReadOnlyList<string> bullets = BuildNewsreelBullets(world, tick);
        IReadOnlyList<BlackLedgerActionBeatViewModel> actionBeats = BuildActionBeats(seed, tick.Turn, world, tick);
        BlackLedgerNewsreelBroadcastViewModel? broadcast = BuildBroadcastPackage(world, tick, transitionLabel, newsreelLead, bullets, actionBeats, ledgerBasePath);
        IReadOnlyList<string> validationChecks =
        [
            $"Receipt-backed transition: {transitionLabel}",
            $"Tick receipt: {tick.ReceiptId}",
            $"Public-safe effects carried: {tick.Effects.Count}",
            $"Dispatch lane: {ledgerBasePath.TrimEnd('/')}/turns/{tick.Turn}/dispatches",
            "No private campaign labels, support records, or sourcebook text are allowed in this packet."
        ];

        return new BlackLedgerWorldTurnBriefingViewModel(
            WorldId: world.WorldId,
            WorldName: world.PublicName,
            FromTurn: fromTurn,
            ToTurn: tick.Turn,
            TransitionLabel: transitionLabel,
            TransitionNarrative: transitionNarrative,
            StateSummary: stateSummary,
            InboxHeadline: inboxHeadline,
            NewsreelLead: newsreelLead,
            ActionBeats: actionBeats,
            NewsreelBullets: bullets,
            ValidationChecks: validationChecks,
            ValidationJsonHref: validationJsonHref,
            Broadcast: broadcast);
    }

    public BlackLedgerFactionLeaderDigestViewModel? BuildLeaderDigest(string factionId, int? requestedTurn, string accountBasePath = "/account/ledger")
    {
        BlackLedgerWorldPreviewViewModel? world = _stats.LoadWorldPreview(requestedTurn);
        BlackLedgerFactionDetailDto? faction = _factions.GetWorkspaceFactionDetail(factionId);
        BlackLedgerTickReceiptViewModel? tick = world?.LastTick;
        if (world is null || faction is null || tick is null)
        {
            return null;
        }

        string normalizedFactionId = faction.FactionId.Replace('_', '-');
        BlackLedgerFactionViewModel? publicFaction = world.Factions.FirstOrDefault(item =>
            string.Equals(item.Id, faction.FactionId, StringComparison.OrdinalIgnoreCase)
            || string.Equals(item.Id.Replace('_', '-'), normalizedFactionId, StringComparison.OrdinalIgnoreCase));
        BlackLedgerDistrictViewModel[] coveredDistricts = world.Districts
            .Where(district => string.Equals(NormalizeSlug(district.DominantFaction), NormalizeSlug(faction.FactionId), StringComparison.OrdinalIgnoreCase))
            .ToArray();
        BlackLedgerTickEffectViewModel[] relevantEffects = tick.Effects
            .Where(effect =>
                NormalizeSlug(effect.Target).Contains(NormalizeSlug(faction.PublicName), StringComparison.OrdinalIgnoreCase)
                || NormalizeSlug(effect.Target).Contains(NormalizeSlug(faction.FactionId), StringComparison.OrdinalIgnoreCase))
            .ToArray();

        var pressureCalls = new List<string>();
        pressureCalls.AddRange(coveredDistricts.Take(2).Select(district =>
            $"{district.Name}: influence {district.Influence}, heat {district.Heat}, trend {district.Trend}, delta {district.DeltaSinceLastTick}."));
        pressureCalls.AddRange(relevantEffects.Select(effect =>
            $"{effect.Metric}: {(effect.Delta >= 0 ? "+" : string.Empty)}{effect.Delta} because {effect.PublicReason}"));
        foreach (string signal in faction.PublicSignals)
        {
            if (pressureCalls.Count >= 5)
            {
                break;
            }

            pressureCalls.Add($"Signal watch: {signal}.");
        }

        if (pressureCalls.Count == 0)
        {
            pressureCalls.Add("No private-only data was promoted here, so the digest falls back to public faction signals and the city-wide turn receipt.");
        }

        var recommendedActions = new List<string>();
        if (coveredDistricts.Any(static district => district.Heat >= 70))
        {
            recommendedActions.Add("Prioritize heat control in your hottest district before trying to widen surface area.");
        }

        if (coveredDistricts.Any(static district => district.Trend.Contains("rising", StringComparison.OrdinalIgnoreCase)))
        {
            recommendedActions.Add("Treat rising districts as validation targets: collect receipts before you claim momentum publicly.");
        }

        if (relevantEffects.Any(static effect => effect.Delta > 0))
        {
            recommendedActions.Add("Convert positive turn movement into one public-safe dispatch beat and one internal action receipt, not a vague hype post.");
        }

        if (recommendedActions.Count == 0)
        {
            recommendedActions.Add("Use Turn 1 as your first clean benchmark: one pressure claim, one evidence trail, one next action.");
        }

        recommendedActions.Add("Keep all world-tick messaging subordinate to the city receipt and never let the ad lane outrun the actual board state.");

        string heading = $"{faction.PublicName} leader brief";
        string summary = $"Personalized digest for {faction.FactionLeader}. This readout turns the public world tick into faction-specific pressure, visible district posture, and bounded next actions.";
        string validationHref = $"{accountBasePath.TrimEnd('/')}/factions/{normalizedFactionId}/leader-briefing.json";

        return new BlackLedgerFactionLeaderDigestViewModel(
            FactionId: normalizedFactionId,
            PublicName: faction.PublicName,
            LeaderHandle: publicFaction?.FactionLeader ?? faction.FactionLeader,
            Heading: heading,
            Summary: summary,
            PressureCalls: pressureCalls.Take(6).ToArray(),
            RecommendedActions: recommendedActions.Take(4).ToArray(),
            ValidationHref: validationHref);
    }

    public BlackLedgerWorldTickValidationPacketViewModel? BuildValidationPacket(
        int? requestedTurn,
        string? factionId,
        string accountBasePath = "/account/ledger",
        string ledgerBasePath = "/ledger")
    {
        BlackLedgerWorldTurnBriefingViewModel? briefing = BuildWorldTurnBriefing(requestedTurn, ledgerBasePath);
        if (briefing is null)
        {
            return null;
        }

        BlackLedgerFactionLeaderDigestViewModel? digest = string.IsNullOrWhiteSpace(factionId)
            ? null
            : BuildLeaderDigest(factionId, requestedTurn, accountBasePath);
        string summary = digest is null
            ? $"{briefing.TransitionLabel} validation packet for the inbox/newsreel lane."
            : $"{briefing.TransitionLabel} validation packet plus leader-specific readout for {digest.PublicName}.";
        List<string> checks =
        [
            ..briefing.ValidationChecks,
            $"World route: {ledgerBasePath.TrimEnd('/')}/turns/{briefing.ToTurn}",
            $"Notification route: {accountBasePath.TrimEnd('/')}/notifications"
        ];
        if (digest is not null)
        {
            checks.Add($"Leader digest route: {accountBasePath.TrimEnd('/')}/factions/{digest.FactionId}/leader-briefing");
        }

        List<string> links =
        [
            $"{ledgerBasePath.TrimEnd('/')}/turns/{briefing.ToTurn}",
            $"{ledgerBasePath.TrimEnd('/')}/turns/{briefing.ToTurn}/dispatches",
            $"{accountBasePath.TrimEnd('/')}/notifications"
        ];
        if (digest is not null)
        {
            links.Add($"{accountBasePath.TrimEnd('/')}/factions/{digest.FactionId}/leader-briefing");
        }

        return new BlackLedgerWorldTickValidationPacketViewModel(
            WorldId: briefing.WorldId,
            WorldName: briefing.WorldName,
            ToTurn: briefing.ToTurn,
            Summary: summary,
            Checks: checks,
            Links: links);
    }

    private static IReadOnlyList<string> BuildNewsreelBullets(BlackLedgerWorldPreviewViewModel world, BlackLedgerTickReceiptViewModel tick)
    {
        List<string> bullets = tick.Effects
            .Select(effect => $"{effect.Target}: {effect.PublicReason}")
            .Take(4)
            .ToList();
        if (bullets.Count < 4)
        {
            bullets.AddRange(world.Districts
                .OrderByDescending(static district => Math.Abs(district.DeltaSinceLastTick))
                .ThenByDescending(static district => district.Heat)
                .Select(district => $"{district.Name}: heat {district.Heat}, influence {district.Influence}, trend {district.Trend}.")
                .Where(item => bullets.All(existing => !string.Equals(existing, item, StringComparison.Ordinal)))
                .Take(4 - bullets.Count));
        }

        return bullets;
    }

    private static string BuildStateSummary(BlackLedgerWorldPreviewViewModel world)
    {
        BlackLedgerDistrictViewModel hottest = world.Districts.OrderByDescending(static district => district.Heat).First();
        BlackLedgerDistrictViewModel sharpestMove = world.Districts.OrderByDescending(static district => Math.Abs(district.DeltaSinceLastTick)).First();
        return $"{hottest.Name} is the hottest visible district at {hottest.Heat} heat. {sharpestMove.Name} moved the hardest this turn with delta {sharpestMove.DeltaSinceLastTick}.";
    }

    private static BlackLedgerNewsreelBroadcastViewModel? BuildBroadcastPackage(
        BlackLedgerWorldPreviewViewModel world,
        BlackLedgerTickReceiptViewModel tick,
        string transitionLabel,
        string newsreelLead,
        IReadOnlyList<string> bullets,
        IReadOnlyList<BlackLedgerActionBeatViewModel> actionBeats,
        string ledgerBasePath)
    {
        string slug = $"turn-{tick.Turn}-newsreel";
        string relativeRoot = Path.Combine("media", "ledger", "newsreels");
        string mp4Path = ResolveMediaFile(Path.Combine(relativeRoot, $"{slug}.mp4"));
        string webmPath = ResolveMediaFile(Path.Combine(relativeRoot, $"{slug}.webm"));
        string posterPath = ResolveMediaFile(Path.Combine(relativeRoot, $"{slug}-poster.png"));
        string captionsPath = ResolveMediaFile(Path.Combine(relativeRoot, $"{slug}.vtt"));
        if (!File.Exists(mp4Path) || !File.Exists(posterPath) || !File.Exists(captionsPath))
        {
            return null;
        }

        string mp4Href = BuildVersionedMediaHref(Path.Combine(relativeRoot, $"{slug}.mp4"));
        string webmHref = File.Exists(webmPath)
            ? BuildVersionedMediaHref(Path.Combine(relativeRoot, $"{slug}.webm"))
            : mp4Href;
        string posterHref = BuildVersionedMediaHref(Path.Combine(relativeRoot, $"{slug}-poster.png"));
        string captionsHref = BuildVersionedMediaHref(Path.Combine(relativeRoot, $"{slug}.vtt"));
        string watchHref = $"{ledgerBasePath.TrimEnd('/')}/newsroom/{slug}";
        string transcriptHref = $"{ledgerBasePath.TrimEnd('/')}/newsroom/{slug}/transcript";
        string receiptsHref = $"{ledgerBasePath.TrimEnd('/')}/newsroom/{slug}/receipts";
        string publishedLabel = new DateTimeOffset(File.GetLastWriteTimeUtc(mp4Path)).ToString("MMMM d, yyyy HH:mm 'UTC'", CultureInfo.InvariantCulture);
        IReadOnlyList<string> rundown =
        [
            $"Open on anchor desk: {transitionLabel} with receipt {tick.ReceiptId}.",
            $"{world.TurnHeadline}",
            ..actionBeats.Take(4).Select(static beat => $"{beat.ActorLabel}: {beat.CommandIntent}"),
            ..actionBeats.Take(3).Select(static beat => beat.ConsequenceLine),
            ..bullets.Take(2).Select(static item => item.TrimEnd('.')),
            BuildStateSummary(world)
        ];
        IReadOnlyList<string> ticker =
        [
            $"{world.PublicName} live",
            $"Turn {tick.Turn} receipt-backed",
            ..actionBeats.Take(3).Select(static beat => beat.VisualHook),
            $"{world.Districts.OrderByDescending(static district => district.Heat).First().Name} hottest district",
            $"{world.Districts.OrderByDescending(static district => Math.Abs(district.DeltaSinceLastTick)).First().Name} biggest move",
            "No player identities or private table state"
        ];
        IReadOnlyList<BlackLedgerCinematicSceneViewModel> screenplayScenes =
        [
            new(
                SceneId: $"turn-{tick.Turn}-anchor-open",
                Label: "Anchor Open",
                DurationLabel: "00:08",
                Purpose: "Open on the turn boundary and establish why this board move matters now.",
                VisualDirection: $"Anchor desk, city incident wall, and receipt {tick.ReceiptId} already live on the lower third.",
                NarratorLine: $"{transitionLabel} for {world.PublicName}. {newsreelLead}"),
            new(
                SceneId: $"turn-{tick.Turn}-field-pressure",
                Label: "Field Pressure",
                DurationLabel: "00:08",
                Purpose: "Translate abstract board pressure into something a player can feel as consequence.",
                VisualDirection: actionBeats.FirstOrDefault()?.VisualHook ?? "Public field pressure moves behind the reporter.",
                NarratorLine: actionBeats.FirstOrDefault()?.ConsequenceLine ?? "Pressure is visible, local, and no longer hypothetical."),
            new(
                SceneId: $"turn-{tick.Turn}-command-rundown",
                Label: "Command Rundown",
                DurationLabel: "00:08",
                Purpose: "Show who moved, what changed, and which lane is heating fastest.",
                VisualDirection: BuildStateSummary(world),
                NarratorLine: BuildStateSummary(world)),
            new(
                SceneId: $"turn-{tick.Turn}-validation-close",
                Label: "Validation Close",
                DurationLabel: "00:06",
                Purpose: "Close on the receipts and keep the bulletin subordinate to proof.",
                VisualDirection: "Validation packet, receipts lane, and captions route remain visible in frame.",
                NarratorLine: "The bulletin can be dramatic, but the receipts still get the last word.")
        ];

        return new BlackLedgerNewsreelBroadcastViewModel(
            PackageLabel: $"Turn {tick.Turn} anchor package",
            AnchorName: "Mara Quill",
            DeskLabel: "Black Ledger Network",
            ProviderStatus: "FIRST_PARTY_NEWSREEL",
            RenderMode: "first_party_anchor_bulletin",
            StorylineSummary: "Each turn bulletin opens on the boundary, translates pressure into visible consequences, and closes on the validation lane.",
            NarratorPosture: "Continuous newsroom narration over a ducked synthetic score bed.",
            RenderPipelineLabel: "First-party bulletin render -> narration mix -> captions -> public newsroom route",
            WatchHref: watchHref,
            TranscriptHref: transcriptHref,
            ReceiptsHref: receiptsHref,
            VideoMp4Href: mp4Href,
            VideoWebmHref: webmHref,
            PosterHref: posterHref,
            CaptionsHref: captionsHref,
            AudioPosture: "Voice-led bulletin with lower-third stingers",
            MusicPosture: "First-party synthetic score bed with ducked narration",
            DurationLabel: "00:16",
            PublishedLabel: publishedLabel,
            EpisodeTypeLabel: "Turn newsreel",
            PublicSafetyNote: "Public-safe bulletin built from aggregate Black Ledger world receipts. No private campaign table data or sourcebook text is exposed here.",
            ReconstructionNote: "Some footage is reconstructed from public-safe receipts. Source records stay available for review.",
            FeedbackHref: "/feedback",
            ActionBeats: actionBeats,
            Rundown: rundown,
            TickerItems: ticker,
            ScreenplayScenes: screenplayScenes);
    }

    private static IReadOnlyList<BlackLedgerActionBeatViewModel> BuildActionBeats(
        BlackLedgerPublicStatsService.BlackLedgerWorldSeedDocument? seed,
        int turn,
        BlackLedgerWorldPreviewViewModel world,
        BlackLedgerTickReceiptViewModel tick)
    {
        BlackLedgerPublicStatsService.BlackLedgerTurnDocument? turnDocument = seed?.Turns?
            .FirstOrDefault(item => item.Turn == turn);
        if (turnDocument?.ActionBeats?.Count > 0)
        {
            return turnDocument.ActionBeats
                .Take(6)
                .Select(static beat => new BlackLedgerActionBeatViewModel(
                    BeatId: string.IsNullOrWhiteSpace(beat.BeatId) ? Guid.NewGuid().ToString("N") : beat.BeatId,
                    ActorKind: string.IsNullOrWhiteSpace(beat.ActorKind) ? "world" : beat.ActorKind,
                    ActorLabel: string.IsNullOrWhiteSpace(beat.ActorLabel) ? "World desk" : beat.ActorLabel,
                    BeatLabel: string.IsNullOrWhiteSpace(beat.BeatLabel) ? "Visible move" : beat.BeatLabel,
                    ActionSummary: beat.ActionSummary,
                    Stakes: beat.Stakes,
                    ProofNote: beat.ProofNote,
                    VisualHook: string.IsNullOrWhiteSpace(beat.VisualHook) ? $"Focus {beat.ActorLabel} pressure on the live globe." : beat.VisualHook,
                    CommandIntent: string.IsNullOrWhiteSpace(beat.CommandIntent) ? $"Track {beat.BeatLabel} as a live board move." : beat.CommandIntent,
                    ConsequenceLine: string.IsNullOrWhiteSpace(beat.ConsequenceLine) ? beat.Stakes : beat.ConsequenceLine))
                .ToArray();
        }

        return tick.Effects
            .Take(4)
            .Select((effect, index) => new BlackLedgerActionBeatViewModel(
                BeatId: $"derived-beat-{index + 1}",
                ActorKind: "faction",
                ActorLabel: effect.Target,
                BeatLabel: effect.Metric,
                ActionSummary: effect.PublicReason,
                Stakes: $"{world.PublicName} visible pressure moved on the city board.",
                ProofNote: $"Board record: {tick.ReceiptId}",
                VisualHook: $"Flash {effect.Target} across the globe while {effect.Metric} moves.",
                CommandIntent: $"Push {effect.Target} onto the command board as a live {effect.Metric} shift.",
                ConsequenceLine: $"{effect.Target} now changes what players and GMs have to answer next."))
            .ToArray();
    }

    private static string BuildVersionedMediaHref(string relativePath)
    {
        string normalized = relativePath.Replace('\\', '/');
        string fullPath = ResolveMediaFile(relativePath);
        long stamp = File.Exists(fullPath)
            ? new DateTimeOffset(File.GetLastWriteTimeUtc(fullPath)).ToUnixTimeSeconds()
            : DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        return $"/{normalized}?v={stamp.ToString(CultureInfo.InvariantCulture)}";
    }

    private static string ResolveMediaFile(string relativePath)
    {
        string normalized = relativePath.Replace('/', Path.DirectorySeparatorChar).Replace('\\', Path.DirectorySeparatorChar);
        string[] candidates =
        [
            Path.Combine(AppContext.BaseDirectory, "wwwroot", normalized),
            Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "Chummer.Run.Api", "wwwroot", normalized)),
            Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "Chummer.Run.Api", "wwwroot", normalized)),
        ];

        foreach (string candidate in candidates)
        {
            if (File.Exists(candidate))
            {
                return candidate;
            }
        }

        return candidates[0];
    }

    private static string NormalizeSlug(string value)
        => value.Trim().Replace('_', '-').ToLowerInvariant();
}
