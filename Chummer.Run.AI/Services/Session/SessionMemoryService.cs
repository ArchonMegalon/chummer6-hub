using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace Chummer.Run.AI.Services.Session;

public interface ISessionMemoryService
{
    SessionMemoryDraftResult Draft(SessionMemoryDraftRequest request, string? sceneId = null);
}

public sealed class SessionMemoryService : ISessionMemoryService
{
    private const string RecapCanonTarget = "canon.session-recap.v1";
    private const string TimelineCanonTarget = "canon.session-timeline.v1";
    private const string UnresolvedCanonTarget = "canon.unresolved-thread.v1";
    private const string RelationshipCanonTarget = "canon.relationship-change.v1";
    private const string MemoryCandidateCanonTarget = "canon.memory-candidate.v1";
    private static readonly Regex TranscriptSpeakerPattern = new(
        @"^(?<speaker>[A-Za-z0-9 _'\-]+)\s*:\s*(?<content>.+)$",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    private readonly ISessionLedgerService _ledger;

    public SessionMemoryService(ISessionLedgerService ledger)
    {
        _ledger = ledger;
    }

    public SessionMemoryDraftResult Draft(SessionMemoryDraftRequest request, string? sceneId = null)
    {
        var targetScene = sceneId ?? request.SceneId ?? string.Empty;
        var events = string.IsNullOrWhiteSpace(targetScene)
            ? _ledger.GetEvents(request.SessionId, "default")
            : _ledger.GetEvents(request.SessionId, targetScene);
        var transcriptLines = CollectTranscriptLines(request);
        var externalSignals = CollectExternalSignals(request, transcriptLines);
        var generatedAtUtc = DateTimeOffset.UtcNow;

        if (events.Count == 0)
        {
            return DraftWithoutLedger(request, targetScene, externalSignals, generatedAtUtc);
        }

        var unresolvedDrafts = BuildUnresolvedThreadDrafts(events, transcriptLines);
        var timelineEntries = BuildTimelineEntries(events, transcriptLines);
        var relationshipDrafts = BuildRelationshipChangeDrafts(events, transcriptLines);
        var relationshipChanges = relationshipDrafts
            .Select(draft => draft.Summary)
            .Distinct(StringComparer.Ordinal)
            .ToList();
        var memoryCandidateDrafts = BuildMemoryCandidateDrafts(unresolvedDrafts, timelineEntries, relationshipDrafts);
        var recapDraft = BuildRecapDraft(events, transcriptLines, unresolvedDrafts, targetScene);
        var confidence = CalculateConfidence(events.Count, transcriptLines.Count, unresolvedDrafts.Count);

        return new SessionMemoryDraftResult(
            SessionId: request.SessionId,
            SceneId: string.IsNullOrWhiteSpace(targetScene) ? null : targetScene,
            Recap: recapDraft.ShortText,
            UnresolvedHooks: unresolvedDrafts.Select(thread => thread.Title).ToList(),
            TimelineDrafts: timelineEntries.Select(FormatTimelineLine).ToList(),
            RelationshipChanges: relationshipChanges,
            RecapDraft: recapDraft,
            UnresolvedThreadDrafts: unresolvedDrafts,
            TimelineEntries: timelineEntries,
            RelationshipChangeDrafts: relationshipDrafts,
            MemoryCandidateDrafts: memoryCandidateDrafts,
            ProposedCanonTargets: new[] { RecapCanonTarget, TimelineCanonTarget, UnresolvedCanonTarget, RelationshipCanonTarget, MemoryCandidateCanonTarget },
            Confidence: confidence,
            GeneratedAtUtc: generatedAtUtc);
    }

    private static SessionMemoryDraftResult DraftWithoutLedger(
        SessionMemoryDraftRequest request,
        string targetScene,
        IReadOnlyList<TranscriptSignal> externalSignals,
        DateTimeOffset generatedAtUtc)
    {
        var highlights = externalSignals.Take(3).Select(signal => signal.Text).ToList();
        var recapText = externalSignals.Count == 0
            ? "No canonical delta events are available yet for this session slice."
            : $"Draft context assembled from {externalSignals.Count} transcript or note signal(s) for scene '{targetScene}'.";
        var recapDraft = new SessionRecapDraft(
            Title: string.IsNullOrWhiteSpace(targetScene) ? "Session recap draft" : $"Session recap draft for {targetScene}",
            ShortText: recapText,
            LongText: recapText,
            Highlights: highlights,
            Evidence: externalSignals.Take(5)
                .Select(signal => signal.Evidence("transcript"))
                .ToList(),
            DraftState: "draft",
            ProposedCanonTarget: RecapCanonTarget);

        return new SessionMemoryDraftResult(
            SessionId: request.SessionId,
            SceneId: string.IsNullOrWhiteSpace(targetScene) ? null : targetScene,
            Recap: recapDraft.ShortText,
            UnresolvedHooks: highlights,
            TimelineDrafts: Array.Empty<string>(),
            RelationshipChanges: Array.Empty<string>(),
            RecapDraft: recapDraft,
            UnresolvedThreadDrafts: Array.Empty<SessionUnresolvedThreadDraft>(),
            TimelineEntries: Array.Empty<SessionTimelineDraftEntry>(),
            RelationshipChangeDrafts: Array.Empty<SessionRelationshipChangeDraft>(),
            MemoryCandidateDrafts: BuildTranscriptOnlyMemoryCandidateDrafts(externalSignals),
            ProposedCanonTargets: new[] { RecapCanonTarget, TimelineCanonTarget, UnresolvedCanonTarget, RelationshipCanonTarget, MemoryCandidateCanonTarget },
            Confidence: externalSignals.Count == 0 ? 0.1d : 0.18d,
            GeneratedAtUtc: generatedAtUtc);
    }

    private static IReadOnlyList<TranscriptSignal> CollectTranscriptLines(SessionMemoryDraftRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.Transcript))
        {
            return Array.Empty<TranscriptSignal>();
        }

        var lines = request.Transcript.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        var collected = new List<TranscriptSignal>(lines.Length);
        for (var index = 0; index < lines.Length; index++)
        {
            var line = lines[index];
            var match = TranscriptSpeakerPattern.Match(line);
            var speaker = match.Success ? match.Groups["speaker"].Value.Trim() : null;
            var content = match.Success ? match.Groups["content"].Value.Trim() : line.Trim();
            if (string.IsNullOrWhiteSpace(content))
            {
                continue;
            }

            collected.Add(new TranscriptSignal($"transcript:{index + 1}", content, speaker));
        }

        return collected;
    }

    private static IReadOnlyList<TranscriptSignal> CollectExternalSignals(
        SessionMemoryDraftRequest request,
        IReadOnlyList<TranscriptSignal> transcriptLines)
    {
        var signals = new List<TranscriptSignal>(transcriptLines.Count + 4);
        signals.AddRange(transcriptLines);

        if (!string.IsNullOrWhiteSpace(request.Notes))
        {
            signals.Add(new TranscriptSignal("note:gm", request.Notes.Trim(), "GM note"));
        }

        if (request.PlayerMessages is { Count: > 0 })
        {
            for (var index = 0; index < request.PlayerMessages.Count; index++)
            {
                var message = request.PlayerMessages[index];
                if (string.IsNullOrWhiteSpace(message))
                {
                    continue;
                }

                signals.Add(new TranscriptSignal($"player:{index + 1}", message.Trim(), "Player message"));
            }
        }

        return signals;
    }

    private static IReadOnlyList<SessionUnresolvedThreadDraft> BuildUnresolvedThreadDrafts(
        IReadOnlyList<SessionEventEnvelope> events,
        IReadOnlyList<TranscriptSignal> transcriptLines)
    {
        var drafts = new Dictionary<string, ThreadAccumulator>(StringComparer.Ordinal);

        foreach (var evt in events)
        {
            if (!LooksUnresolved(evt.EventType, evt.Payload))
            {
                continue;
            }

            var key = NormalizeKey(evt.Payload);
            if (!drafts.TryGetValue(key, out var accumulator))
            {
                accumulator = new ThreadAccumulator(evt.Payload);
                drafts[key] = accumulator;
            }

            accumulator.AddEvidence(new SessionMemoryEvidence(
                Kind: "ledger-event",
                Reference: evt.EventId,
                Detail: $"{evt.EventType}: {evt.Payload}"));
        }

        foreach (var signal in transcriptLines)
        {
            if (!LooksUnresolved(signal.Speaker, signal.Text))
            {
                continue;
            }

            var key = NormalizeKey(signal.Text);
            if (!drafts.TryGetValue(key, out var accumulator))
            {
                accumulator = new ThreadAccumulator(signal.Text);
                drafts[key] = accumulator;
            }

            accumulator.AddEvidence(signal.Evidence("transcript"));
        }

        return drafts.Values
            .OrderByDescending(item => item.MentionCount)
            .ThenBy(item => item.Title, StringComparer.Ordinal)
            .Select(item => new SessionUnresolvedThreadDraft(
                ThreadId: $"thread-{NormalizeKey(item.Title)}",
                Title: ToTitle(item.Title),
                Summary: $"Draft unresolved thread for approval: {item.Title}",
                Status: "open",
                MentionCount: item.MentionCount,
                Evidence: item.Evidence,
                DraftState: "draft",
                ProposedCanonTarget: UnresolvedCanonTarget))
            .ToList();
    }

    private static IReadOnlyList<SessionTimelineDraftEntry> BuildTimelineEntries(
        IReadOnlyList<SessionEventEnvelope> events,
        IReadOnlyList<TranscriptSignal> transcriptLines)
    {
        var entries = new List<SessionTimelineDraftEntry>(events.Count + transcriptLines.Count);

        entries.AddRange(events
            .OrderBy(evt => evt.AtUtc)
            .ThenBy(evt => evt.EventId, StringComparer.Ordinal)
            .Select(evt => new SessionTimelineDraftEntry(
                EntryId: $"timeline:{evt.EventId}",
                Summary: $"{evt.EventType}: {evt.Payload}",
                AtUtc: evt.AtUtc,
                SourceKind: "ledger-event",
                Evidence: new[]
                {
                    new SessionMemoryEvidence("ledger-event", evt.EventId, $"{evt.EventType}: {evt.Payload}")
                },
                DraftState: "draft",
                ProposedCanonTarget: TimelineCanonTarget)));

        entries.AddRange(transcriptLines.Select(signal => new SessionTimelineDraftEntry(
            EntryId: signal.Reference,
            Summary: signal.Speaker is null ? signal.Text : $"{signal.Speaker}: {signal.Text}",
            AtUtc: null,
            SourceKind: "transcript",
            Evidence: new[]
            {
                signal.Evidence("transcript")
            },
            DraftState: "draft",
            ProposedCanonTarget: TimelineCanonTarget)));

        return entries
            .OrderBy(entry => entry.AtUtc ?? DateTimeOffset.MaxValue)
            .ThenBy(entry => entry.EntryId, StringComparer.Ordinal)
            .Take(16)
            .ToList();
    }

    private static IReadOnlyList<SessionRelationshipChangeDraft> BuildRelationshipChangeDrafts(
        IReadOnlyList<SessionEventEnvelope> events,
        IReadOnlyList<TranscriptSignal> transcriptLines)
    {
        var drafts = new Dictionary<string, RelationshipAccumulator>(StringComparer.Ordinal);

        foreach (var evt in events)
        {
            if (!LooksLikeRelationshipSignal(evt.EventType, evt.Payload))
            {
                continue;
            }

            var key = NormalizeKey(evt.Payload);
            if (!drafts.TryGetValue(key, out var accumulator))
            {
                accumulator = new RelationshipAccumulator(evt.Payload, InferRelationshipChangeKind(evt.EventType, evt.Payload));
                drafts[key] = accumulator;
            }

            accumulator.AddEvidence(new SessionMemoryEvidence(
                Kind: "ledger-event",
                Reference: evt.EventId,
                Detail: $"{evt.EventType}: {evt.Payload}"));
        }

        foreach (var signal in transcriptLines)
        {
            if (!LooksLikeRelationshipSignal(signal.Speaker, signal.Text))
            {
                continue;
            }

            var key = NormalizeKey(signal.Text);
            if (!drafts.TryGetValue(key, out var accumulator))
            {
                accumulator = new RelationshipAccumulator(signal.Text, InferRelationshipChangeKind(signal.Speaker, signal.Text));
                drafts[key] = accumulator;
            }

            accumulator.AddEvidence(signal.Evidence("transcript"));
        }

        return drafts.Values
            .OrderByDescending(item => item.MentionCount)
            .ThenBy(item => item.Summary, StringComparer.Ordinal)
            .Select(item => new SessionRelationshipChangeDraft(
                ChangeId: $"relationship-{NormalizeKey(item.Summary)}",
                Summary: $"Relationship shift candidate: {item.Summary}",
                ChangeKind: item.ChangeKind,
                Impact: InferRelationshipImpact(item.Summary),
                MentionCount: item.MentionCount,
                Confidence: Math.Min(0.94d, 0.48d + Math.Min(item.MentionCount, 4) * 0.11d),
                Evidence: item.Evidence,
                DraftState: "draft",
                ProposedCanonTarget: RelationshipCanonTarget))
            .ToList();
    }

    private static IReadOnlyList<SessionMemoryCandidateDraft> BuildMemoryCandidateDrafts(
        IReadOnlyList<SessionUnresolvedThreadDraft> unresolvedDrafts,
        IReadOnlyList<SessionTimelineDraftEntry> timelineEntries,
        IReadOnlyList<SessionRelationshipChangeDraft> relationshipDrafts)
    {
        var candidates = new List<SessionMemoryCandidateDraft>();

        candidates.AddRange(relationshipDrafts.Select(draft => new SessionMemoryCandidateDraft(
            CandidateId: $"memory:{draft.ChangeId}",
            Category: "relationship",
            Title: ToTitle(draft.ChangeKind.Replace('-', ' ')),
            Summary: draft.Summary,
            CanonScope: "persona-relationship",
            Confidence: draft.Confidence,
            Evidence: draft.Evidence,
            DraftState: "draft",
            ProposedCanonTarget: MemoryCandidateCanonTarget)));

        candidates.AddRange(unresolvedDrafts.Take(3).Select(draft => new SessionMemoryCandidateDraft(
            CandidateId: $"memory:{draft.ThreadId}",
            Category: "unresolved-thread",
            Title: draft.Title,
            Summary: draft.Summary,
            CanonScope: "session-thread",
            Confidence: Math.Min(0.92d, 0.46d + Math.Min(draft.MentionCount, 4) * 0.1d),
            Evidence: draft.Evidence,
            DraftState: "draft",
            ProposedCanonTarget: MemoryCandidateCanonTarget)));

        candidates.AddRange(timelineEntries
            .Where(entry => entry.SourceKind == "ledger-event")
            .Take(3)
            .Select(entry => new SessionMemoryCandidateDraft(
                CandidateId: $"memory:{NormalizeKey(entry.EntryId)}",
                Category: "timeline-fact",
                Title: entry.AtUtc is null ? "Timeline fact" : $"Timeline fact at {entry.AtUtc.Value:HH:mm:ss}",
                Summary: entry.Summary,
                CanonScope: "session-timeline",
                Confidence: entry.SourceKind == "ledger-event" ? 0.72d : 0.42d,
                Evidence: entry.Evidence,
                DraftState: "draft",
                ProposedCanonTarget: MemoryCandidateCanonTarget)));

        return candidates
            .GroupBy(candidate => candidate.CandidateId, StringComparer.Ordinal)
            .Select(static group => group.First())
            .OrderByDescending(candidate => candidate.Confidence)
            .ThenBy(candidate => candidate.CandidateId, StringComparer.Ordinal)
            .ToList();
    }

    private static IReadOnlyList<SessionMemoryCandidateDraft> BuildTranscriptOnlyMemoryCandidateDrafts(
        IReadOnlyList<TranscriptSignal> externalSignals)
    {
        return externalSignals
            .Take(3)
            .Select((signal, index) => new SessionMemoryCandidateDraft(
                CandidateId: $"memory:transcript-{index + 1}",
                Category: "transcript-signal",
                Title: signal.Speaker is null ? "Transcript signal" : $"{signal.Speaker} signal",
                Summary: signal.Text,
                CanonScope: "session-note",
                Confidence: 0.24d,
                Evidence: new[] { signal.Evidence("transcript") },
                DraftState: "draft",
                ProposedCanonTarget: MemoryCandidateCanonTarget))
            .ToList();
    }

    private static SessionRecapDraft BuildRecapDraft(
        IReadOnlyList<SessionEventEnvelope> events,
        IReadOnlyList<TranscriptSignal> transcriptLines,
        IReadOnlyList<SessionUnresolvedThreadDraft> unresolvedDrafts,
        string targetScene)
    {
        var eventTypes = events
            .GroupBy(evt => evt.EventType, StringComparer.OrdinalIgnoreCase)
            .OrderByDescending(group => group.Count())
            .ThenBy(group => group.Key, StringComparer.OrdinalIgnoreCase)
            .Take(3)
            .Select(group => $"{group.Key} x{group.Count()}")
            .ToList();
        var highlights = new List<string>();
        highlights.AddRange(events
            .OrderBy(evt => evt.AtUtc)
            .Take(3)
            .Select(evt => $"{evt.EventType}: {evt.Payload}"));
        highlights.AddRange(transcriptLines
            .Take(2)
            .Select(signal => signal.Speaker is null ? signal.Text : $"{signal.Speaker}: {signal.Text}"));

        var sceneLabel = string.IsNullOrWhiteSpace(targetScene) ? "current session slice" : $"scene '{targetScene}'";
        var shortText = new StringBuilder()
            .Append($"Draft recap for {sceneLabel}: {events.Count} ledger event(s)")
            .Append(eventTypes.Count == 0 ? "." : $", led by {string.Join(", ", eventTypes)}.")
            .Append(unresolvedDrafts.Count == 0 ? string.Empty : $" {unresolvedDrafts.Count} unresolved thread draft(s) remain open.")
            .ToString();
        var longText = transcriptLines.Count == 0
            ? $"{shortText} No transcript lines were provided for supplemental narrative context."
            : $"{shortText} Transcript signals captured {transcriptLines.Count} additional line(s) for approval review.";

        var evidence = events
            .Take(4)
            .Select(evt => new SessionMemoryEvidence("ledger-event", evt.EventId, $"{evt.EventType}: {evt.Payload}"))
            .Concat(transcriptLines.Take(2).Select(signal => signal.Evidence("transcript")))
            .ToList();

        return new SessionRecapDraft(
            Title: string.IsNullOrWhiteSpace(targetScene) ? "Session recap draft" : $"Session recap draft for {targetScene}",
            ShortText: shortText,
            LongText: longText,
            Highlights: highlights.Distinct(StringComparer.Ordinal).Take(5).ToList(),
            Evidence: evidence,
            DraftState: "draft",
            ProposedCanonTarget: RecapCanonTarget);
    }

    private static double CalculateConfidence(int eventCount, int transcriptLineCount, int unresolvedCount)
    {
        var score = 0.35d;
        score += Math.Min(eventCount, 24) * 0.018d;
        score += Math.Min(transcriptLineCount, 12) * 0.012d;
        score += Math.Min(unresolvedCount, 4) * 0.01d;
        return Math.Min(0.97d, score);
    }

    private static string FormatTimelineLine(SessionTimelineDraftEntry entry)
    {
        var prefix = entry.AtUtc is null
            ? entry.SourceKind
            : entry.AtUtc.Value.ToString("HH:mm:ss", CultureInfo.InvariantCulture);
        return $"{prefix} {entry.Summary}";
    }

    private static bool LooksUnresolved(string? first, string second)
    {
        return ContainsUnresolvedMarker(first) || ContainsUnresolvedMarker(second) || second.Contains('?');
    }

    private static bool ContainsUnresolvedMarker(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        return value.Contains("unresolved", StringComparison.OrdinalIgnoreCase)
            || value.Contains("open", StringComparison.OrdinalIgnoreCase)
            || value.Contains("hook", StringComparison.OrdinalIgnoreCase)
            || value.Contains("lead", StringComparison.OrdinalIgnoreCase)
            || value.Contains("follow up", StringComparison.OrdinalIgnoreCase);
    }

    private static bool LooksLikeRelationshipSignal(string? first, string second)
    {
        return ContainsRelationshipMarker(first) || ContainsRelationshipMarker(second);
    }

    private static bool ContainsRelationshipMarker(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        return value.Contains("relationship", StringComparison.OrdinalIgnoreCase)
            || value.Contains("trust", StringComparison.OrdinalIgnoreCase)
            || value.Contains("loyal", StringComparison.OrdinalIgnoreCase)
            || value.Contains("ally", StringComparison.OrdinalIgnoreCase)
            || value.Contains("suspicion", StringComparison.OrdinalIgnoreCase)
            || value.Contains("betray", StringComparison.OrdinalIgnoreCase)
            || value.Contains("respect", StringComparison.OrdinalIgnoreCase)
            || value.Contains("rep", StringComparison.OrdinalIgnoreCase)
            || value.Contains("bond", StringComparison.OrdinalIgnoreCase)
            || value.Contains("debt", StringComparison.OrdinalIgnoreCase);
    }

    private static string InferRelationshipChangeKind(string? first, string second)
    {
        var combined = $"{first} {second}";
        if (combined.Contains("trust", StringComparison.OrdinalIgnoreCase) || combined.Contains("ally", StringComparison.OrdinalIgnoreCase))
        {
            return "trust-shift";
        }

        if (combined.Contains("loyal", StringComparison.OrdinalIgnoreCase) || combined.Contains("bond", StringComparison.OrdinalIgnoreCase))
        {
            return "bond-shift";
        }

        if (combined.Contains("betray", StringComparison.OrdinalIgnoreCase) || combined.Contains("suspicion", StringComparison.OrdinalIgnoreCase))
        {
            return "risk-shift";
        }

        if (combined.Contains("debt", StringComparison.OrdinalIgnoreCase) || combined.Contains("rep", StringComparison.OrdinalIgnoreCase))
        {
            return "standing-shift";
        }

        return "relationship-shift";
    }

    private static string InferRelationshipImpact(string value)
    {
        if (value.Contains("increase", StringComparison.OrdinalIgnoreCase)
            || value.Contains("improve", StringComparison.OrdinalIgnoreCase)
            || value.Contains("trust", StringComparison.OrdinalIgnoreCase)
            || value.Contains("ally", StringComparison.OrdinalIgnoreCase))
        {
            return "positive";
        }

        if (value.Contains("decrease", StringComparison.OrdinalIgnoreCase)
            || value.Contains("betray", StringComparison.OrdinalIgnoreCase)
            || value.Contains("suspicion", StringComparison.OrdinalIgnoreCase)
            || value.Contains("hostile", StringComparison.OrdinalIgnoreCase))
        {
            return "negative";
        }

        return "mixed";
    }

    private static string NormalizeKey(string value)
    {
        var builder = new StringBuilder(value.Length);
        foreach (var character in value.Trim().ToLowerInvariant())
        {
            if (char.IsLetterOrDigit(character))
            {
                builder.Append(character);
            }
            else if (builder.Length == 0 || builder[^1] != '-')
            {
                builder.Append('-');
            }
        }

        return builder.ToString().Trim('-');
    }

    private static string ToTitle(string value)
    {
        var normalized = value.Trim();
        return string.IsNullOrWhiteSpace(normalized)
            ? "Unresolved thread"
            : char.ToUpperInvariant(normalized[0]) + normalized[1..];
    }

    private sealed record TranscriptSignal(string Reference, string Text, string? Speaker)
    {
        public SessionMemoryEvidence Evidence(string kind)
        {
            var detail = Speaker is null ? Text : $"{Speaker}: {Text}";
            return new SessionMemoryEvidence(kind, Reference, detail);
        }
    }

    private sealed class ThreadAccumulator
    {
        private readonly List<SessionMemoryEvidence> _evidence = new();

        public ThreadAccumulator(string title)
        {
            Title = title.Trim();
        }

        public string Title { get; }
        public int MentionCount => _evidence.Count;
        public IReadOnlyList<SessionMemoryEvidence> Evidence => _evidence;

        public void AddEvidence(SessionMemoryEvidence evidence)
        {
            if (_evidence.Any(existing => string.Equals(existing.Reference, evidence.Reference, StringComparison.Ordinal)))
            {
                return;
            }

            _evidence.Add(evidence);
        }
    }

    private sealed class RelationshipAccumulator
    {
        private readonly List<SessionMemoryEvidence> _evidence = new();

        public RelationshipAccumulator(string summary, string changeKind)
        {
            Summary = summary.Trim();
            ChangeKind = changeKind;
        }

        public string Summary { get; }
        public string ChangeKind { get; }
        public int MentionCount => _evidence.Count;
        public IReadOnlyList<SessionMemoryEvidence> Evidence => _evidence;

        public void AddEvidence(SessionMemoryEvidence evidence)
        {
            if (_evidence.Any(existing => string.Equals(existing.Reference, evidence.Reference, StringComparison.Ordinal)))
            {
                return;
            }

            _evidence.Add(evidence);
        }
    }
}
