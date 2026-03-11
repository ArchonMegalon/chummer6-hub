using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Contracts.Observability;

namespace Chummer.Run.AI.Services.Session;

public interface ISessionLedgerService
{
    Task<SessionRelayMergeResponse> MergeEventsAsync(IReadOnlyList<SessionEventEnvelope> events, CancellationToken cancellationToken = default);
    SessionEventProjectionDto GetProjection(string sessionId, string sceneId);
    IReadOnlyList<SessionEventEnvelope> GetEvents(string sessionId, string sceneId);
    Chummer.Run.Contracts.Relay.SessionLedgerBackupPackage ExportBackup();
    void RestoreBackup(Chummer.Run.Contracts.Relay.SessionLedgerBackupPackage backup);
    PipelineProjection GetRelayPipelineProjection();
}

public sealed class SessionLedgerService : ISessionLedgerService
{
    private sealed class SceneState
    {
        public List<SessionEventEnvelope> Events { get; set; } = new();
    }

    private readonly ConcurrentDictionary<string, SceneState> _states = new();
    private readonly ConcurrentQueue<PipelineDeadLetterEntry> _deadLetters = new();
    private long _processedEvents;
    private long _duplicateEvents;
    private long _ignoredEvents;
    private long _acceptedEvents;
    private long _idempotencyReplayCount;
    private DateTimeOffset? _lastReplayAtUtc;

    public Task<SessionRelayMergeResponse> MergeEventsAsync(IReadOnlyList<SessionEventEnvelope> events, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (events.Count == 0)
        {
            return Task.FromResult(
                new SessionRelayMergeResponse(
                    SessionId: string.Empty,
                    SceneId: string.Empty,
                    AcceptedEvents: 0,
                    DuplicateEvents: 0,
                    IgnoredEvents: 0,
                    Projection: BuildProjection(string.Empty, string.Empty, Array.Empty<SessionEventEnvelope>()),
                    MergedAtUtc: DateTimeOffset.UtcNow,
                    Diagnostics: BuildDiagnostics(string.Empty, string.Empty, 0, 0, 0, 0, "empty", false)));
        }

        var firstEvent = events[0];
        var filteredEvents = events
            .Where(item => string.Equals(item.SessionId, firstEvent.SessionId, StringComparison.Ordinal)
                && string.Equals(item.SceneId, firstEvent.SceneId, StringComparison.Ordinal))
            .Where(item => !string.IsNullOrWhiteSpace(item.EventId))
            .ToList();
        var ignoredEvents = events.Count - filteredEvents.Count;
        Interlocked.Add(ref _processedEvents, events.Count);
        if (ignoredEvents > 0)
        {
            Interlocked.Add(ref _ignoredEvents, ignoredEvents);
            EnqueueDeadLetter(
                itemId: $"{firstEvent.SessionId}:{firstEvent.SceneId}:{Guid.NewGuid():N}",
                reason: "relay-ignored-invalid-or-wrong-scene",
                fingerprint: $"{firstEvent.SessionId}:{firstEvent.SceneId}");
        }
        if (filteredEvents.Count == 0)
        {
            return Task.FromResult(new SessionRelayMergeResponse(
                SessionId: firstEvent.SessionId,
                SceneId: firstEvent.SceneId,
                AcceptedEvents: 0,
                DuplicateEvents: 0,
                IgnoredEvents: ignoredEvents,
                Projection: BuildProjection(firstEvent.SessionId, firstEvent.SceneId, Array.Empty<SessionEventEnvelope>()),
                MergedAtUtc: DateTimeOffset.UtcNow,
                Diagnostics: BuildDiagnostics(firstEvent.SessionId, firstEvent.SceneId, events.Count, 0, 0, ignoredEvents, "empty", false)));
        }

        var key = ComposeKey(firstEvent.SessionId, firstEvent.SceneId);
        var sceneState = _states.GetOrAdd(key, _ => new SceneState());

        lock (sceneState)
        {
            var currentIds = new HashSet<string>(sceneState.Events.Select(x => x.EventId), StringComparer.Ordinal);
            var acceptedEvents = 0;
            var duplicateEvents = 0;
            foreach (var item in filteredEvents)
            {
                if (currentIds.Add(item.EventId))
                {
                    sceneState.Events.Add(item);
                    acceptedEvents++;
                }
                else
                {
                    duplicateEvents++;
                }
            }
            Interlocked.Add(ref _acceptedEvents, acceptedEvents);
            Interlocked.Add(ref _duplicateEvents, duplicateEvents);
            if (duplicateEvents > 0)
            {
                Interlocked.Add(ref _idempotencyReplayCount, duplicateEvents);
                _lastReplayAtUtc = DateTimeOffset.UtcNow;
            }

            var ordered = sceneState.Events
                .OrderBy(item => item.AtUtc)
                .ThenBy(item => item.EventId)
                .ToList();
            sceneState.Events.Clear();
            sceneState.Events.AddRange(ordered);

            var projection = BuildProjection(firstEvent.SessionId, firstEvent.SceneId, ordered);
            return Task.FromResult(new SessionRelayMergeResponse(
                SessionId: firstEvent.SessionId,
                SceneId: firstEvent.SceneId,
                AcceptedEvents: acceptedEvents,
                DuplicateEvents: duplicateEvents,
                IgnoredEvents: ignoredEvents,
                Projection: projection,
                MergedAtUtc: projection.GeneratedAtUtc,
                Diagnostics: BuildDiagnostics(
                    firstEvent.SessionId,
                    firstEvent.SceneId,
                    events.Count,
                    acceptedEvents,
                    duplicateEvents,
                    ignoredEvents,
                    projection.ProjectionFingerprint,
                    acceptedEvents + duplicateEvents == filteredEvents.Count)));
        }
    }

    public SessionEventProjectionDto GetProjection(string sessionId, string sceneId)
    {
        var events = GetEvents(sessionId, sceneId);
        return BuildProjection(sessionId, sceneId, events);
    }

    public IReadOnlyList<SessionEventEnvelope> GetEvents(string sessionId, string sceneId)
    {
        var key = ComposeKey(sessionId, sceneId);
        if (!_states.TryGetValue(key, out var sceneState))
        {
            return Array.Empty<SessionEventEnvelope>();
        }

        lock (sceneState)
        {
            return sceneState.Events.ToArray();
        }
    }

    public PipelineProjection GetRelayPipelineProjection()
    {
        var activeScenes = _states.Count;
        var failed = 0;
        return new PipelineProjection(
            Pipeline: "relay",
            Observability: new PipelineObservabilityProjection(
                ProcessedCount: ToInt(_processedEvents),
                ActiveCount: activeScenes,
                SucceededCount: ToInt(_acceptedEvents),
                FailedCount: failed,
                DuplicateCount: ToInt(_duplicateEvents),
                IgnoredCount: ToInt(_ignoredEvents)),
            Idempotency: new PipelineIdempotencyProjection(
                TrackedKeys: CountTrackedRelayKeys(),
                ReplayCount: ToInt(_idempotencyReplayCount),
                LastReplayAtUtc: _lastReplayAtUtc),
            Cost: new PipelineCostProjection(
                EstimatedUsd: 0,
                BudgetUnitsConsumed: 0),
            DeadLetter: new PipelineDeadLetterProjection(
                Count: _deadLetters.Count,
                Recent: _deadLetters.Take(25).ToArray()));
    }

    public Chummer.Run.Contracts.Relay.SessionLedgerBackupPackage ExportBackup()
    {
        var scenes = _states
            .OrderBy(item => item.Key, StringComparer.Ordinal)
            .Select(item =>
            {
                var split = item.Key.Split("::", 2, StringSplitOptions.None);
                var sessionId = split.Length > 0 ? split[0] : string.Empty;
                var sceneId = split.Length > 1 ? split[1] : string.Empty;
                lock (item.Value)
                {
                    return new Chummer.Run.Contracts.Relay.SessionLedgerSceneBackup(
                        SessionId: sessionId,
                        SceneId: sceneId,
                        Events: item.Value.Events.Select(ToRunEvent).ToArray());
                }
            })
            .ToArray();

        return new Chummer.Run.Contracts.Relay.SessionLedgerBackupPackage(
            ExportedAtUtc: DateTimeOffset.UtcNow,
            Scenes: scenes,
            DeadLetters: _deadLetters.ToArray(),
            ProcessedEvents: Interlocked.Read(ref _processedEvents),
            AcceptedEvents: Interlocked.Read(ref _acceptedEvents),
            DuplicateEvents: Interlocked.Read(ref _duplicateEvents),
            IgnoredEvents: Interlocked.Read(ref _ignoredEvents),
            IdempotencyReplayCount: Interlocked.Read(ref _idempotencyReplayCount),
            LastReplayAtUtc: _lastReplayAtUtc);
    }

    public void RestoreBackup(Chummer.Run.Contracts.Relay.SessionLedgerBackupPackage backup)
    {
        if (!string.Equals(backup.ContractFamily, "session_state_backup_v1", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Session ledger backups must use contract family 'session_state_backup_v1'.");
        }

        _states.Clear();
        foreach (var scene in backup.Scenes)
        {
            if (string.IsNullOrWhiteSpace(scene.SessionId) || string.IsNullOrWhiteSpace(scene.SceneId))
            {
                continue;
            }

            var key = ComposeKey(scene.SessionId.Trim(), scene.SceneId.Trim());
            var normalizedEvents = scene.Events
                .Where(item =>
                    string.Equals(item.SessionId, scene.SessionId, StringComparison.Ordinal)
                    && string.Equals(item.SceneId, scene.SceneId, StringComparison.Ordinal)
                    && !string.IsNullOrWhiteSpace(item.EventId))
                .OrderBy(item => item.AtUtc)
                .ThenBy(item => item.EventId, StringComparer.Ordinal)
                .ToList();
            var deduped = new List<SessionEventEnvelope>(normalizedEvents.Count);
            var seenIds = new HashSet<string>(StringComparer.Ordinal);
            foreach (var item in normalizedEvents)
            {
                if (seenIds.Add(item.EventId))
                {
                    deduped.Add(ToPlayEvent(item));
                }
            }

            _states[key] = new SceneState { Events = deduped };
        }

        while (_deadLetters.TryDequeue(out _))
        {
        }
        foreach (var deadLetter in backup.DeadLetters)
        {
            _deadLetters.Enqueue(deadLetter);
        }
        while (_deadLetters.Count > 200 && _deadLetters.TryDequeue(out _))
        {
        }

        Interlocked.Exchange(ref _processedEvents, backup.ProcessedEvents);
        Interlocked.Exchange(ref _acceptedEvents, backup.AcceptedEvents);
        Interlocked.Exchange(ref _duplicateEvents, backup.DuplicateEvents);
        Interlocked.Exchange(ref _ignoredEvents, backup.IgnoredEvents);
        Interlocked.Exchange(ref _idempotencyReplayCount, backup.IdempotencyReplayCount);
        _lastReplayAtUtc = backup.LastReplayAtUtc;
    }

    private static string ComposeKey(string sessionId, string sceneId) =>
        $"{sessionId}::{sceneId}";

    private static SessionEventProjectionDto BuildProjection(
        string sessionId,
        string sceneId,
        IReadOnlyList<SessionEventEnvelope> events)
    {
        return new SessionEventProjectionDto(
            SessionId: sessionId,
            SceneId: sceneId,
            Version: events.Count,
            ProjectionFingerprint: ComputeEventFingerprint(events),
            GeneratedAtUtc: DateTimeOffset.UtcNow,
            Events: events.ToArray());
    }

    private static SessionRelayConvergenceDiagnostics BuildDiagnostics(
        string sessionId,
        string sceneId,
        int submittedEvents,
        int acceptedEvents,
        int duplicateEvents,
        int ignoredEvents,
        string projectionFingerprint,
        bool converged)
    {
        return new SessionRelayConvergenceDiagnostics(
            ContractFamily: "session_events_vnext",
            SubmittedEvents: submittedEvents,
            AcceptedEvents: acceptedEvents,
            DuplicateEvents: duplicateEvents,
            IgnoredEvents: ignoredEvents,
            SceneIdentity: $"{sessionId}:{sceneId}",
            ProjectionFingerprint: projectionFingerprint,
            Converged: converged,
            EvaluatedAtUtc: DateTimeOffset.UtcNow);
    }

    private static string ComputeEventFingerprint(IReadOnlyList<SessionEventEnvelope> events)
    {
        if (events.Count == 0)
        {
            return "empty";
        }

        using var sha = SHA256.Create();
        var payload = string.Join("|", events.Select(
            @event => $"{@event.EventId}:{@event.EventType}:{@event.Payload}:{@event.AtUtc:O}"));
        var bytes = Encoding.UTF8.GetBytes(payload);
        var hash = sha.ComputeHash(bytes);
        return Convert.ToHexString(hash);
    }

    private void EnqueueDeadLetter(string itemId, string reason, string? fingerprint)
    {
        _deadLetters.Enqueue(new PipelineDeadLetterEntry(
            ItemId: itemId,
            Reason: reason,
            OccurredAtUtc: DateTimeOffset.UtcNow,
            Fingerprint: fingerprint));
        while (_deadLetters.Count > 200 && _deadLetters.TryDequeue(out _))
        {
        }
    }

    private int CountTrackedRelayKeys()
    {
        var tracked = 0;
        foreach (var scene in _states.Values)
        {
            lock (scene)
            {
                tracked += scene.Events.Count;
            }
        }

        return tracked;
    }

    private static int ToInt(long value) => value > int.MaxValue ? int.MaxValue : (int)value;

    private static Chummer.Run.Contracts.Relay.SessionEventEnvelope ToRunEvent(SessionEventEnvelope source) =>
        new(
            SessionId: source.SessionId,
            SceneId: source.SceneId,
            EventType: source.EventType,
            Payload: source.Payload,
            AtUtc: source.AtUtc,
            EventId: source.EventId,
            SceneRevision: source.SceneRevision,
            IdempotencyKey: source.IdempotencyKey,
            ContractFamily: source.ContractFamily);

    private static SessionEventEnvelope ToPlayEvent(Chummer.Run.Contracts.Relay.SessionEventEnvelope source) =>
        new(
            SessionId: source.SessionId,
            SceneId: source.SceneId,
            EventType: source.EventType,
            Payload: source.Payload,
            AtUtc: source.AtUtc,
            EventId: source.EventId,
            SceneRevision: source.SceneRevision,
            IdempotencyKey: source.IdempotencyKey,
            ContractFamily: source.ContractFamily);
}
