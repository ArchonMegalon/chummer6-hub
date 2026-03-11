using System.Collections.Concurrent;

namespace Chummer.Run.AI.Services.Spider;

public interface IDeliveryOutboxService
{
    DeliveryOutboxMessage Enqueue(DeliveryOutboxCreateRequest request);
    IReadOnlyList<DeliveryOutboxMessage> GetForScene(string sessionId, string sceneId, string? currentSceneRevision = null);
    DeliveryOutboxMessage? GetById(string messageId);
    DeliveryOutboxMessage? RecordAction(
        string messageId,
        SpiderActionExecutionState execution,
        string cardStatus,
        string? approvalState = null,
        DateTimeOffset? hiddenUntilUtc = null);
}

public sealed class DeliveryOutboxService : IDeliveryOutboxService
{
    private sealed record OutboxRecord(
        string Id,
        string SessionId,
        string SceneId,
        string SceneRevision,
        string Channel,
        string Content,
        DateTimeOffset EnqueuedAtUtc,
        DateTimeOffset? StaleAfterUtc,
        DateTimeOffset? HiddenUntilUtc,
        string AutonomyMode,
        string ApprovalState,
        DateTimeOffset? SceneStartedAtUtc,
        string ProjectionFingerprint,
        string CollaborationMode,
        SpiderTacticalCard? Card);

    private readonly ConcurrentDictionary<string, List<OutboxRecord>> _outbox = new();
    private readonly object _mutate = new();

    public DeliveryOutboxMessage Enqueue(DeliveryOutboxCreateRequest request)
    {
        var id = Guid.NewGuid().ToString("N");
        var now = DateTimeOffset.UtcNow;
        var staleAfter = request.Ttl is null
            ? now.AddMinutes(5)
            : now.Add(request.Ttl.Value);

        var canonical = new OutboxRecord(
            Id: id,
            SessionId: request.SessionId,
            SceneId: request.SceneId,
            SceneRevision: request.SceneRevision,
            Channel: request.Channel,
            Content: request.Content,
            EnqueuedAtUtc: now,
            StaleAfterUtc: staleAfter,
            HiddenUntilUtc: request.HiddenUntilUtc,
            AutonomyMode: request.AutonomyMode,
            ApprovalState: request.ApprovalState,
            SceneStartedAtUtc: request.SceneStartedAtUtc ?? now,
            ProjectionFingerprint: request.ProjectionFingerprint,
            CollaborationMode: request.CollaborationMode,
            Card: request.Card);

        var key = ComposeKey(request.SessionId, request.SceneId);
        var sceneList = _outbox.GetOrAdd(key, _ => new List<OutboxRecord>());
        lock (_mutate)
        {
            sceneList.Add(canonical);
        }

        return new DeliveryOutboxMessage(
            Id: id,
            SessionId: request.SessionId,
            SceneId: request.SceneId,
            SceneRevision: request.SceneRevision,
            Channel: request.Channel,
            Content: request.Content,
            ApprovalState: request.ApprovalState,
            AutonomyMode: request.AutonomyMode,
            EnqueuedAtUtc: now,
            StaleAfter: request.Ttl,
            HiddenUntilUtc: request.HiddenUntilUtc,
            ProjectionFingerprint: request.ProjectionFingerprint,
            CollaborationMode: request.CollaborationMode,
            Card: request.Card);
    }

    public IReadOnlyList<DeliveryOutboxMessage> GetForScene(string sessionId, string sceneId, string? currentSceneRevision = null)
    {
        var key = ComposeKey(sessionId, sceneId);
        if (!_outbox.TryGetValue(key, out var sceneList))
        {
            return Array.Empty<DeliveryOutboxMessage>();
        }

        var now = DateTimeOffset.UtcNow;
        lock (_mutate)
        {
            for (var index = 0; index < sceneList.Count; index++)
            {
                var item = sceneList[index];
                var expired = item.StaleAfterUtc.HasValue && item.StaleAfterUtc < now;
                var staleRevision = !string.IsNullOrWhiteSpace(currentSceneRevision)
                    && !string.Equals(item.SceneRevision, currentSceneRevision, StringComparison.Ordinal);
                if (!expired && !staleRevision)
                {
                    continue;
                }

                sceneList[index] = MarkStale(item, now, staleRevision ? "revision-mismatch" : "ttl-expired");
            }

            if (string.IsNullOrWhiteSpace(currentSceneRevision))
            {
                currentSceneRevision = sceneList
                    .OrderByDescending(item => item.SceneStartedAtUtc ?? item.EnqueuedAtUtc)
                    .Select(item => item.SceneRevision)
                    .FirstOrDefault();
            }

            if (string.IsNullOrWhiteSpace(currentSceneRevision))
            {
                return Array.Empty<DeliveryOutboxMessage>();
            }

            var applicable = sceneList
                .Where(item => !item.HiddenUntilUtc.HasValue || item.HiddenUntilUtc <= now)
                .Where(item => string.Equals(item.SceneRevision, currentSceneRevision, StringComparison.Ordinal))
                .Where(item => !item.StaleAfterUtc.HasValue || item.StaleAfterUtc >= now)
                .Where(item => !string.Equals(item.Card?.Status, "stale", StringComparison.Ordinal))
                .Select(item => new DeliveryOutboxMessage(
                    Id: item.Id,
                    SessionId: item.SessionId,
                    SceneId: item.SceneId,
                    SceneRevision: item.SceneRevision,
                    Channel: item.Channel,
                    Content: item.Content,
                    ApprovalState: item.ApprovalState,
                    AutonomyMode: item.AutonomyMode,
                    EnqueuedAtUtc: item.EnqueuedAtUtc,
                    StaleAfter: item.StaleAfterUtc.HasValue ? item.StaleAfterUtc.Value - item.EnqueuedAtUtc : null,
                    HiddenUntilUtc: item.HiddenUntilUtc,
                    ProjectionFingerprint: item.ProjectionFingerprint,
                    CollaborationMode: item.CollaborationMode,
                    Card: item.Card))
                .ToArray();

            return applicable;
        }
    }

    public DeliveryOutboxMessage? GetById(string messageId)
    {
        lock (_mutate)
        {
            foreach (var entry in _outbox.Values)
            {
                var record = entry.FirstOrDefault(item => string.Equals(item.Id, messageId, StringComparison.Ordinal));
                if (record is not null)
                {
                    return ToMessage(record);
                }
            }
        }

        return null;
    }

    public DeliveryOutboxMessage? RecordAction(
        string messageId,
        SpiderActionExecutionState execution,
        string cardStatus,
        string? approvalState = null,
        DateTimeOffset? hiddenUntilUtc = null)
    {
        lock (_mutate)
        {
            foreach (var entry in _outbox.Values)
            {
                var index = entry.FindIndex(item => string.Equals(item.Id, messageId, StringComparison.Ordinal));
                if (index < 0)
                {
                    continue;
                }

                var current = entry[index];
                var updatedCard = current.Card is null
                    ? null
                    : current.Card with
                    {
                        Status = cardStatus,
                        ActionExecutions = (current.Card.ActionExecutions ?? Array.Empty<SpiderActionExecutionState>())
                            .Concat(new[] { execution })
                            .OrderBy(item => item.ExecutedAtUtc)
                            .ToArray()
                    };

                var updated = current with
                {
                    HiddenUntilUtc = hiddenUntilUtc ?? current.HiddenUntilUtc,
                    ApprovalState = approvalState ?? current.ApprovalState,
                    Card = updatedCard
                };

                entry[index] = updated;
                return ToMessage(updated);
            }
        }

        return null;
    }

    private static string ComposeKey(string sessionId, string sceneId) => $"{sessionId}::{sceneId}";

    private static DeliveryOutboxMessage ToMessage(OutboxRecord item)
    {
        return new DeliveryOutboxMessage(
            Id: item.Id,
            SessionId: item.SessionId,
            SceneId: item.SceneId,
            SceneRevision: item.SceneRevision,
            Channel: item.Channel,
            Content: item.Content,
            ApprovalState: item.ApprovalState,
            AutonomyMode: item.AutonomyMode,
            EnqueuedAtUtc: item.EnqueuedAtUtc,
            StaleAfter: item.StaleAfterUtc.HasValue ? item.StaleAfterUtc.Value - item.EnqueuedAtUtc : null,
            HiddenUntilUtc: item.HiddenUntilUtc,
            ProjectionFingerprint: item.ProjectionFingerprint,
            CollaborationMode: item.CollaborationMode,
            Card: item.Card);
    }

    private static OutboxRecord MarkStale(OutboxRecord item, DateTimeOffset now, string reason)
    {
        var updatedCard = item.Card is null
            ? null
            : item.Card with
            {
                Status = "stale",
                Payload = (item.Card.Payload ?? new SpiderTacticalPayload()) with
                {
                    IsStaleDraft = true,
                    DraftState = $"stale:{reason}",
                    BudgetAllowed = false
                },
                StaleAfterUtc = item.StaleAfterUtc ?? now
            };

        return item with
        {
            ApprovalState = string.Equals(item.ApprovalState, "approved", StringComparison.OrdinalIgnoreCase)
                ? "approved"
                : "stale",
            Card = updatedCard
        };
    }
}
