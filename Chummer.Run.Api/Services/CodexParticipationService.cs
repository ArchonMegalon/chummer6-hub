using System.Collections.Concurrent;

namespace Chummer.Run.Api.Services;

public sealed record CodexParticipationEvent(
    string EventId,
    string Kind,
    string Message,
    DateTimeOffset CreatedAtUtc);

public sealed record CodexParticipationIntentSnapshot(
    string IntentId,
    string SubjectId,
    string SubjectLabel,
    string ProjectId,
    string RequestedLaneType,
    string Status,
    bool Consented,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset? ConsentedAtUtc,
    DateTimeOffset? RevokedAtUtc,
    string? FleetLaneId,
    IReadOnlyList<CodexParticipationEvent> Events);

internal sealed class CodexParticipationIntentState
{
    public string IntentId { get; init; } = "";
    public string SubjectId { get; init; } = "";
    public string SubjectLabel { get; set; } = "";
    public string ProjectId { get; init; } = "";
    public string RequestedLaneType { get; init; } = "participant_burst";
    public string Status { get; set; } = "created";
    public bool Consented { get; set; }
    public DateTimeOffset CreatedAtUtc { get; init; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? ConsentedAtUtc { get; set; }
    public DateTimeOffset? RevokedAtUtc { get; set; }
    public string? FleetLaneId { get; set; }
    public List<CodexParticipationEvent> Events { get; } = new();
    public object Gate { get; } = new();
}

public sealed class CodexParticipationService
{
    private readonly ConcurrentDictionary<string, CodexParticipationIntentState> _intents = new(StringComparer.OrdinalIgnoreCase);

    public CodexParticipationIntentSnapshot CreateIntent(string subjectId, string subjectLabel, string projectId)
    {
        var now = DateTimeOffset.UtcNow;
        var state = new CodexParticipationIntentState
        {
            IntentId = $"intent-{Guid.NewGuid():N}"[..17],
            SubjectId = subjectId.Trim(),
            SubjectLabel = string.IsNullOrWhiteSpace(subjectLabel) ? subjectId.Trim() : subjectLabel.Trim(),
            ProjectId = projectId.Trim(),
            CreatedAtUtc = now
        };
        state.Events.Add(new CodexParticipationEvent(
            EventId: $"evt-{Guid.NewGuid():N}"[..17],
            Kind: "intent_created",
            Message: $"Created participation intent for {state.ProjectId}.",
            CreatedAtUtc: now));
        _intents[state.IntentId] = state;
        return Snapshot(state);
    }

    public CodexParticipationIntentSnapshot? GetIntent(string intentId)
    {
        return _intents.TryGetValue(intentId.Trim(), out var state) ? Snapshot(state) : null;
    }

    public IReadOnlyList<CodexParticipationEvent> GetEvents(string intentId)
    {
        if (!_intents.TryGetValue(intentId.Trim(), out var state))
        {
            return Array.Empty<CodexParticipationEvent>();
        }

        lock (state.Gate)
        {
            return state.Events.ToArray();
        }
    }

    public CodexParticipationIntentSnapshot RecordConsent(string intentId)
    {
        var state = Require(intentId);
        lock (state.Gate)
        {
            state.Consented = true;
            state.ConsentedAtUtc ??= DateTimeOffset.UtcNow;
            state.Status = "consented";
            state.Events.Add(new CodexParticipationEvent(
                EventId: $"evt-{Guid.NewGuid():N}"[..17],
                Kind: "consent_recorded",
                Message: "Participant consent was recorded.",
                CreatedAtUtc: DateTimeOffset.UtcNow));
            return Snapshot(state);
        }
    }

    public CodexParticipationIntentSnapshot AttachFleetLane(string intentId, string fleetLaneId, string statusMessage)
    {
        var state = Require(intentId);
        lock (state.Gate)
        {
            state.FleetLaneId = fleetLaneId.Trim();
            state.Status = "fleet_lane_created";
            state.Events.Add(new CodexParticipationEvent(
                EventId: $"evt-{Guid.NewGuid():N}"[..17],
                Kind: "fleet_lane_created",
                Message: statusMessage,
                CreatedAtUtc: DateTimeOffset.UtcNow));
            return Snapshot(state);
        }
    }

    public CodexParticipationIntentSnapshot RecordStatus(string intentId, string status, string message)
    {
        var state = Require(intentId);
        lock (state.Gate)
        {
            state.Status = status.Trim();
            state.Events.Add(new CodexParticipationEvent(
                EventId: $"evt-{Guid.NewGuid():N}"[..17],
                Kind: "status",
                Message: message,
                CreatedAtUtc: DateTimeOffset.UtcNow));
            return Snapshot(state);
        }
    }

    public CodexParticipationIntentSnapshot RecordRevocation(string intentId, string message)
    {
        var state = Require(intentId);
        lock (state.Gate)
        {
            state.Status = "revoked";
            state.RevokedAtUtc ??= DateTimeOffset.UtcNow;
            state.Events.Add(new CodexParticipationEvent(
                EventId: $"evt-{Guid.NewGuid():N}"[..17],
                Kind: "revoked",
                Message: message,
                CreatedAtUtc: DateTimeOffset.UtcNow));
            return Snapshot(state);
        }
    }

    private CodexParticipationIntentState Require(string intentId)
    {
        if (_intents.TryGetValue(intentId.Trim(), out var state))
        {
            return state;
        }

        throw new KeyNotFoundException($"Unknown intent: {intentId}");
    }

    private static CodexParticipationIntentSnapshot Snapshot(CodexParticipationIntentState state)
    {
        lock (state.Gate)
        {
            return new CodexParticipationIntentSnapshot(
                IntentId: state.IntentId,
                SubjectId: state.SubjectId,
                SubjectLabel: state.SubjectLabel,
                ProjectId: state.ProjectId,
                RequestedLaneType: state.RequestedLaneType,
                Status: state.Status,
                Consented: state.Consented,
                CreatedAtUtc: state.CreatedAtUtc,
                ConsentedAtUtc: state.ConsentedAtUtc,
                RevokedAtUtc: state.RevokedAtUtc,
                FleetLaneId: state.FleetLaneId,
                Events: state.Events.ToArray());
        }
    }
}
