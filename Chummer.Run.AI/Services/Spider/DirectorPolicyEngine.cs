
namespace Chummer.Run.AI.Services.Spider;

public interface IDirectorPolicyEngine
{
    PolicyDecision Decide(SpiderObservation observation, FastSignal? signal, SpiderDeepAnalysis? deepAnalysis = null, string? sceneRevision = null);
}

public sealed class DirectorPolicyEngine : IDirectorPolicyEngine
{
    public PolicyDecision Decide(SpiderObservation observation, FastSignal? signal, SpiderDeepAnalysis? deepAnalysis = null, string? sceneRevision = null)
    {
        if (signal is null || !signal.Escalate)
        {
            return new PolicyDecision(
                SessionId: observation.SessionId,
                Action: "hold",
                InterruptionLevel: InterruptionLevel.Off,
                Rationale: "No strong fast signal matched; scene-safe to stay silent.",
                ShouldDeliver: false,
                ExpireAfter: TimeSpan.FromMinutes(1),
                CardKind: "hold",
                CardTitle: "Hold",
                Tags: ["scene-safe"],
                SuggestedActions:
                [
                    new SpiderTacticalAction("mute-1m", "Mute 1m", "Keep Spider silent unless a stronger signal arrives.", "mute", false, "hide-current", "spider.feed.muted")
                ],
                DecisionTier: "fast");
        }

        var payload = observation.Payload ?? string.Empty;
        var baseTags = BuildTags(payload, signal);
        var tags = MergeTags(baseTags, deepAnalysis?.Tags);
        var suggestedActions = MergeActions(
            BuildSuggestedActions(payload, sceneRevision),
            deepAnalysis?.SuggestedActions);
        var evidence = MergeEvidence(
            BuildEvidence(observation, sceneRevision, signal, baseTags),
            deepAnalysis?.Evidence);
        var level = deepAnalysis is null
            ? signal.Confidence >= 85
            ? InterruptionLevel.High
            : signal.Confidence >= 65
                ? InterruptionLevel.Tactical
                : signal.Confidence >= 45
                    ? InterruptionLevel.Low
                    : InterruptionLevel.Off
            : MaxLevel(
                deepAnalysis.RecommendedInterruptionLevel,
                signal.Confidence >= 85
                    ? InterruptionLevel.High
                    : signal.Confidence >= 65
                        ? InterruptionLevel.Tactical
                        : signal.Confidence >= 45
                            ? InterruptionLevel.Low
                            : InterruptionLevel.Off);

        var shouldDeliver = level is not InterruptionLevel.Off;
        var cardKind = string.IsNullOrWhiteSpace(deepAnalysis?.RecommendedCardKind)
            ? DetermineCardKind(tags)
            : deepAnalysis.RecommendedCardKind;
        var cardTitle = string.IsNullOrWhiteSpace(deepAnalysis?.RecommendedCardTitle)
            ? BuildCardTitle(tags, sceneRevision)
            : deepAnalysis.RecommendedCardTitle;
        var nextAction = shouldDeliver
            ? $"deliver tactical card for scene={sceneRevision ?? "unknown"}"
            : "observe only";
        var expireAfter = signal.Confidence >= 65
            ? TimeSpan.FromMinutes(1)
            : TimeSpan.FromMinutes(3);
        var rationale = deepAnalysis is null
            ? $"Fast signal '{signal.Signal}' confidence={signal.Confidence}."
            : $"{deepAnalysis.Summary} Fast signal '{signal.Signal}' confidence={signal.Confidence}.";

        return new PolicyDecision(
            SessionId: observation.SessionId,
            Action: nextAction,
            InterruptionLevel: level,
            Rationale: rationale,
            ShouldDeliver: shouldDeliver,
            ExpireAfter: expireAfter,
            CardKind: cardKind,
            CardTitle: cardTitle,
            Tags: tags,
            SuggestedActions: suggestedActions,
            Evidence: evidence,
            DecisionTier: deepAnalysis is null ? "fast" : "deep",
            DeepAnalysis: deepAnalysis);
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

    private static string BuildCardTitle(IReadOnlyList<string> tags, string? sceneRevision)
    {
        var sceneLabel = string.IsNullOrWhiteSpace(sceneRevision) ? "current scene" : sceneRevision;
        if (tags.Contains("scene-shift", StringComparer.Ordinal))
        {
            return $"Scene shift: {sceneLabel}";
        }

        if (tags.Contains("matrix-heat", StringComparer.Ordinal))
        {
            return $"Matrix heat: {sceneLabel}";
        }

        if (tags.Contains("combat-risk", StringComparer.Ordinal))
        {
            return $"Threat pressure: {sceneLabel}";
        }

        return $"Spider note: {sceneLabel}";
    }

    private static IReadOnlyList<string> BuildTags(string payload, FastSignal signal)
    {
        var tags = new HashSet<string>(StringComparer.Ordinal);
        if (payload.Contains("scene shift", StringComparison.OrdinalIgnoreCase)
            || payload.Contains("transfer to", StringComparison.OrdinalIgnoreCase)
            || payload.Contains("new location", StringComparison.OrdinalIgnoreCase)
            || payload.Contains("cut to", StringComparison.OrdinalIgnoreCase)
            || payload.Contains("fade out", StringComparison.OrdinalIgnoreCase))
        {
            tags.Add("scene-shift");
        }

        if (payload.Contains("god", StringComparison.OrdinalIgnoreCase)
            || payload.Contains("overwatch", StringComparison.OrdinalIgnoreCase)
            || payload.Contains("matrix", StringComparison.OrdinalIgnoreCase))
        {
            tags.Add("matrix-heat");
        }

        if (payload.Contains("alarm", StringComparison.OrdinalIgnoreCase)
            || payload.Contains("drone", StringComparison.OrdinalIgnoreCase)
            || payload.Contains("fireball", StringComparison.OrdinalIgnoreCase))
        {
            tags.Add("combat-risk");
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

    private static IReadOnlyList<SpiderTacticalAction> BuildSuggestedActions(string payload, string? sceneRevision)
    {
        var actions = new List<SpiderTacticalAction>
        {
            new("pin-card", "Pin", "Keep this card visible on the GM ops board.", "pin", false, "annotate-current", "pin.updated"),
            new("snooze-2m", "Snooze 2m", "Hide this card briefly unless a stronger revision arrives.", "snooze", false, "hide-current", "spider.card.snoozed")
        };

        if (payload.Contains("god", StringComparison.OrdinalIgnoreCase)
            || payload.Contains("overwatch", StringComparison.OrdinalIgnoreCase))
        {
            actions.Add(new SpiderTacticalAction(
                "prep-matrix-exit",
                "Prep exit",
                $"Flag a matrix disengage option for {(string.IsNullOrWhiteSpace(sceneRevision) ? "the scene" : sceneRevision)}.",
                "matrix-exit",
                false,
                "queue-follow-up",
                "spider.action.matrix-exit-prep"));
        }

        if (payload.Contains("alarm", StringComparison.OrdinalIgnoreCase)
            || payload.Contains("drone", StringComparison.OrdinalIgnoreCase))
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

        return actions;
    }

    private static IReadOnlyList<EvidencePointer> BuildEvidence(
        SpiderObservation observation,
        string? sceneRevision,
        FastSignal signal,
        IReadOnlyList<string> tags)
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
                Source: "fast-signal-detector")
        };

        if (!string.IsNullOrWhiteSpace(sceneRevision))
        {
            evidence.Add(new EvidencePointer(
                Kind: "scene",
                Reference: sceneRevision,
                Label: $"Scene revision {sceneRevision}",
                Source: "session-ops"));
        }

        foreach (var tag in tags)
        {
            evidence.Add(new EvidencePointer(
                Kind: "tag",
                Reference: tag,
                Label: tag,
                Source: "director-policy"));
        }

        return evidence;
    }

    private static IReadOnlyList<string> MergeTags(
        IReadOnlyList<string> tags,
        IReadOnlyList<string>? additionalTags)
    {
        return tags
            .Concat(additionalTags ?? Array.Empty<string>())
            .Distinct(StringComparer.Ordinal)
            .OrderBy(tag => tag, StringComparer.Ordinal)
            .ToArray();
    }

    private static IReadOnlyList<SpiderTacticalAction> MergeActions(
        IReadOnlyList<SpiderTacticalAction> actions,
        IReadOnlyList<SpiderTacticalAction>? additionalActions)
    {
        return actions
            .Concat(additionalActions ?? Array.Empty<SpiderTacticalAction>())
            .GroupBy(action => action.ActionId, StringComparer.Ordinal)
            .Select(group => group.First())
            .ToArray();
    }

    private static IReadOnlyList<EvidencePointer> MergeEvidence(
        IReadOnlyList<EvidencePointer> evidence,
        IReadOnlyList<EvidencePointer>? additionalEvidence)
    {
        return evidence
            .Concat(additionalEvidence ?? Array.Empty<EvidencePointer>())
            .GroupBy(pointer => $"{pointer.Kind}:{pointer.Reference}", StringComparer.Ordinal)
            .Select(group => group.First())
            .ToArray();
    }

    private static InterruptionLevel MaxLevel(InterruptionLevel left, InterruptionLevel right)
    {
        return (InterruptionLevel)Math.Max((int)left, (int)right);
    }
}
