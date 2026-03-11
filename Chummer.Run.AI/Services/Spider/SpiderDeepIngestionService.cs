using System.Text.Json;
using Chummer.Run.AI.Services.Gateway;
using Chummer.Run.AI.Services.Session;

namespace Chummer.Run.AI.Services.Spider;

public interface ISpiderDeepIngestionService
{
    Task<SpiderDeepAnalysis?> AnalyzeAsync(
        SpiderObservation observation,
        FastSignal signal,
        string sceneId,
        string sceneRevision,
        SessionRuntimeBundleDto bundle,
        CancellationToken cancellationToken);
}

public sealed class SpiderDeepIngestionService : ISpiderDeepIngestionService
{
    private readonly IAiGatewayService _gateway;
    private readonly IPromptRegistry _prompts;
    private readonly ISessionLedgerService _ledger;

    public SpiderDeepIngestionService(
        IAiGatewayService gateway,
        IPromptRegistry prompts,
        ISessionLedgerService ledger)
    {
        _gateway = gateway;
        _prompts = prompts;
        _ledger = ledger;
    }

    public async Task<SpiderDeepAnalysis?> AnalyzeAsync(
        SpiderObservation observation,
        FastSignal signal,
        string sceneId,
        string sceneRevision,
        SessionRuntimeBundleDto bundle,
        CancellationToken cancellationToken)
    {
        if (!signal.Escalate)
        {
            return null;
        }

        var events = _ledger.GetEvents(observation.SessionId, sceneId);
        var evidence = BuildEvidence(observation, signal, sceneRevision, bundle, events);
        var tags = BuildTags(observation, signal, bundle, events);
        var actions = BuildActions(tags, observation.Payload, sceneRevision, bundle.IncludedEventTypes);
        var route = await ExecuteGatewayAsync(observation, signal, sceneId, sceneRevision, bundle, events, evidence, cancellationToken);
        var summary = BuildSummary(signal, bundle, route, tags, events);

        return new SpiderDeepAnalysis(
            SessionId: observation.SessionId,
            SceneId: sceneId,
            SceneRevision: sceneRevision,
            Summary: summary,
            RecommendedCardKind: DetermineCardKind(tags),
            RecommendedCardTitle: BuildCardTitle(tags, sceneRevision),
            RecommendedInterruptionLevel: RecommendInterruptionLevel(signal, tags, events),
            Tags: tags,
            SuggestedActions: actions,
            Evidence: evidence,
            RouteDecision: route.Decision,
            PromptLineage: route.Prompt?.Lineage,
            ProviderOutput: route.Output,
            FocusEventTypes: bundle.IncludedEventTypes);
    }

    private async Task<GatewayInvocation> ExecuteGatewayAsync(
        SpiderObservation observation,
        FastSignal signal,
        string sceneId,
        string sceneRevision,
        SessionRuntimeBundleDto bundle,
        IReadOnlyList<SessionEventEnvelope> events,
        IReadOnlyList<EvidencePointer> evidence,
        CancellationToken cancellationToken)
    {
        var inputs = JsonSerializer.Serialize(new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["sceneRevision"] = sceneRevision,
            ["observation"] = BuildObservationDigest(observation, signal),
            ["eventDigest"] = BuildEventDigest(events)
        });
        var render = _prompts.Render(new PromptRenderRequest(
            TemplateName: "spider.tactical-card",
            Inputs: inputs,
            GroundingContext: new PromptGroundingContext(
                RuntimeFingerprint: bundle.ProjectionFingerprint,
                PackProfileIds: bundle.IncludedEventTypes,
                EvidencePointers: evidence.Select(pointer => pointer.Label).ToArray(),
                RetrievalScope: $"session:{observation.SessionId}/scene:{sceneId}",
                SceneId: sceneId)));

        return await _gateway.ExecuteRouteAsync(new ProviderRouteRequest(
            Purpose: "spider.deep-analysis",
            Prompt: render.RenderedText,
            StructuredOutput: true,
            MaxTokens: 1500,
            SessionId: observation.SessionId,
            Temperature: 0.2,
            PromptLineage: render.Lineage), cancellationToken);
    }

    private static IReadOnlyList<EvidencePointer> BuildEvidence(
        SpiderObservation observation,
        FastSignal signal,
        string sceneRevision,
        SessionRuntimeBundleDto bundle,
        IReadOnlyList<SessionEventEnvelope> events)
    {
        var evidence = new List<EvidencePointer>
        {
            new(
                Kind: "observation",
                Reference: $"observation:{observation.SessionId}:{observation.ObservedAtUtc:yyyyMMddHHmmss}",
                Label: $"Observed via {observation.Source}",
                Source: observation.Source),
            new(
                Kind: "signal",
                Reference: $"signal:{signal.Confidence}",
                Label: signal.Signal,
                Source: "fast-signal-detector"),
            new(
                Kind: "scene",
                Reference: sceneRevision,
                Label: $"Scene revision {sceneRevision}",
                Source: "session-ops"),
            new(
                Kind: "runtime-bundle",
                Reference: bundle.BundleVersion,
                Label: $"Runtime bundle {bundle.BundleVersion}",
                Source: bundle.ProjectionFingerprint)
        };

        foreach (var evt in events.OrderByDescending(item => item.AtUtc).Take(4))
        {
            evidence.Add(new EvidencePointer(
                Kind: "ledger-event",
                Reference: evt.EventId,
                Label: $"{evt.EventType}: {evt.Payload}",
                Source: "session-ledger"));
        }

        return evidence;
    }

    private static IReadOnlyList<string> BuildTags(
        SpiderObservation observation,
        FastSignal signal,
        SessionRuntimeBundleDto bundle,
        IReadOnlyList<SessionEventEnvelope> events)
    {
        var tags = new HashSet<string>(StringComparer.Ordinal);
        var payload = observation.Payload ?? string.Empty;
        var eventTypes = bundle.IncludedEventTypes.Concat(events.Select(evt => evt.EventType));

        if (ContainsAny(payload, eventTypes, "matrix", "overwatch", "god"))
        {
            tags.Add("matrix-heat");
        }

        if (ContainsAny(payload, eventTypes, "alarm", "drone", "combat", "gunfire"))
        {
            tags.Add("combat-risk");
        }

        if (ContainsAny(payload, eventTypes, "scene shift", "transfer", "cut to", "new location", "fade out"))
        {
            tags.Add("scene-shift");
        }

        if (ContainsAny(payload, eventTypes, "corp", "executive", "security"))
        {
            tags.Add("corp-attention");
        }

        if (ContainsAny(payload, eventTypes, "astral", "spirit", "mana", "magic"))
        {
            tags.Add("magical-attention");
        }

        if (bundle.Ready)
        {
            tags.Add("ledger-grounded");
        }

        if (signal.Confidence >= 85)
        {
            tags.Add("urgent");
        }

        if (tags.Count == 0)
        {
            tags.Add("signal");
        }

        return tags.OrderBy(static tag => tag, StringComparer.Ordinal).ToArray();
    }

    private static IReadOnlyList<SpiderTacticalAction> BuildActions(
        IReadOnlyList<string> tags,
        string payload,
        string sceneRevision,
        IReadOnlyList<string> includedEventTypes)
    {
        var actions = new List<SpiderTacticalAction>
        {
            new("pin-card", "Pin", "Keep this card visible on the GM ops board.", "pin", false, "annotate-current", "pin.updated"),
            new("snooze-2m", "Snooze 2m", "Hide this card briefly unless a stronger revision arrives.", "snooze", false, "hide-current", "spider.card.snoozed")
        };

        if (tags.Contains("matrix-heat", StringComparer.Ordinal))
        {
            actions.Add(new SpiderTacticalAction(
                "prep-matrix-exit",
                "Prep exit",
                $"Flag a matrix disengage option for {sceneRevision}.",
                "matrix-exit",
                false,
                "queue-follow-up",
                "spider.action.matrix-exit-prep"));
        }

        if (tags.Contains("combat-risk", StringComparer.Ordinal)
            || ContainsAny(payload, includedEventTypes, "alarm", "drone"))
        {
            actions.Add(new SpiderTacticalAction(
                "reveal-threat",
                "Reveal threat",
                "Queue a player-safe reveal card or screen prompt for the active threat.",
                "player-reveal",
                true,
                "queue-follow-up",
                "spider.action.threat-reveal"));
        }

        if (tags.Contains("scene-shift", StringComparer.Ordinal))
        {
            actions.Add(new SpiderTacticalAction(
                "bind-current-revision",
                "Bind revision",
                $"Pin subsequent drafts to scene revision {sceneRevision}.",
                "bind-revision",
                false,
                "annotate-current",
                "spider.scene.revision-bound"));
        }

        return actions
            .GroupBy(action => action.ActionId, StringComparer.Ordinal)
            .Select(group => group.First())
            .ToArray();
    }

    private static string BuildSummary(
        FastSignal signal,
        SessionRuntimeBundleDto bundle,
        GatewayInvocation route,
        IReadOnlyList<string> tags,
        IReadOnlyList<SessionEventEnvelope> events)
    {
        var eventSummary = events.Count == 0
            ? "no prior ledger events"
            : $"{events.Count} ledger event(s), latest {events[^1].EventType}";
        var delivery = route.Success
            ? $"{route.Decision.SelectedModel} via {route.Decision.Provider}"
            : $"gateway fallback ({route.Error ?? "route error"})";
        return $"Deep Spider ingest grounded on {eventSummary}, bundle {bundle.BundleVersion}, tags [{string.Join(", ", tags)}], route {delivery}; fast confidence {signal.Confidence}.";
    }

    private static string BuildObservationDigest(SpiderObservation observation, FastSignal signal)
    {
        return $"{observation.Source} observed '{observation.Payload}' at {observation.ObservedAtUtc:O} with fast signal {signal.Signal} ({signal.Confidence}).";
    }

    private static string BuildEventDigest(IReadOnlyList<SessionEventEnvelope> events)
    {
        if (events.Count == 0)
        {
            return "no-session-ledger-events";
        }

        return string.Join(" | ", events
            .OrderByDescending(item => item.AtUtc)
            .Take(4)
            .Select(item => $"{item.EventType}:{item.Payload}"));
    }

    private static InterruptionLevel RecommendInterruptionLevel(
        FastSignal signal,
        IReadOnlyList<string> tags,
        IReadOnlyList<SessionEventEnvelope> events)
    {
        if (signal.Confidence >= 90 || tags.Contains("urgent", StringComparer.Ordinal))
        {
            return InterruptionLevel.High;
        }

        if (tags.Contains("combat-risk", StringComparer.Ordinal) || events.Count >= 3)
        {
            return InterruptionLevel.Tactical;
        }

        return signal.Confidence >= 45
            ? InterruptionLevel.Low
            : InterruptionLevel.Off;
    }

    private static string DetermineCardKind(IReadOnlyList<string> tags)
    {
        if (tags.Contains("scene-shift", StringComparer.Ordinal))
        {
            return "scene-shift";
        }

        if (tags.Contains("matrix-heat", StringComparer.Ordinal))
        {
            return "heat";
        }

        if (tags.Contains("combat-risk", StringComparer.Ordinal))
        {
            return "threat";
        }

        return "tactical-note";
    }

    private static string BuildCardTitle(IReadOnlyList<string> tags, string sceneRevision)
    {
        if (tags.Contains("scene-shift", StringComparer.Ordinal))
        {
            return $"Scene shift: {sceneRevision}";
        }

        if (tags.Contains("matrix-heat", StringComparer.Ordinal))
        {
            return $"Matrix heat: {sceneRevision}";
        }

        if (tags.Contains("combat-risk", StringComparer.Ordinal))
        {
            return $"Threat pressure: {sceneRevision}";
        }

        return $"Spider note: {sceneRevision}";
    }

    private static bool ContainsAny(string payload, IEnumerable<string> values, params string[] needles)
    {
        foreach (var needle in needles)
        {
            if (payload.Contains(needle, StringComparison.OrdinalIgnoreCase)
                || values.Any(value => value.Contains(needle, StringComparison.OrdinalIgnoreCase)))
            {
                return true;
            }
        }

        return false;
    }
}
