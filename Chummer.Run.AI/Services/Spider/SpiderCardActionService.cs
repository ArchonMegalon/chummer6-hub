using Chummer.Run.AI.Services.Session;

namespace Chummer.Run.AI.Services.Spider;

public interface ISpiderCardActionService
{
    Task<SpiderActionExecutionResult> ExecuteAsync(
        string messageId,
        string actionId,
        SpiderActionExecuteRequest request,
        CancellationToken cancellationToken);
}

public sealed class SpiderCardActionService : ISpiderCardActionService
{
    private readonly IDeliveryOutboxService _outbox;
    private readonly ISessionLedgerService _ledger;

    public SpiderCardActionService(
        IDeliveryOutboxService outbox,
        ISessionLedgerService ledger)
    {
        _outbox = outbox;
        _ledger = ledger;
    }

    public async Task<SpiderActionExecutionResult> ExecuteAsync(
        string messageId,
        string actionId,
        SpiderActionExecuteRequest request,
        CancellationToken cancellationToken)
    {
        var message = _outbox.GetById(messageId);
        if (message is null)
        {
            return new SpiderActionExecutionResult(messageId, actionId, "missing", "missing", "missing");
        }

        if (!string.Equals(message.SessionId, request.SessionId, StringComparison.Ordinal)
            || !string.Equals(message.SceneId, request.SceneId, StringComparison.Ordinal))
        {
            return new SpiderActionExecutionResult(messageId, actionId, "mismatch", message.ApprovalState, message.Card?.Status ?? "pending", UpdatedMessage: message);
        }

        if (!string.Equals(message.SceneRevision, request.SceneRevision, StringComparison.Ordinal))
        {
            return new SpiderActionExecutionResult(messageId, actionId, "stale", message.ApprovalState, message.Card?.Status ?? "stale", UpdatedMessage: message);
        }

        if (string.Equals(message.Card?.Status, "stale", StringComparison.Ordinal)
            || (message.StaleAfter.HasValue && message.EnqueuedAtUtc + message.StaleAfter.Value < DateTimeOffset.UtcNow))
        {
            return new SpiderActionExecutionResult(messageId, actionId, "stale", message.ApprovalState, "stale", UpdatedMessage: message);
        }

        var action = message.Card?.Actions.FirstOrDefault(item => string.Equals(item.ActionId, actionId, StringComparison.Ordinal));
        if (action is null)
        {
            return new SpiderActionExecutionResult(messageId, actionId, "unsupported", message.ApprovalState, message.Card?.Status ?? "pending", UpdatedMessage: message);
        }

        var now = DateTimeOffset.UtcNow;
        if (action.RequiresApproval && !string.Equals(request.ApprovalState, "approved", StringComparison.OrdinalIgnoreCase))
        {
            var approvalExecution = new SpiderActionExecutionState(
                ActionId: action.ActionId,
                Status: "approval-required",
                PerformedBy: request.RequestedBy,
                ExecutedAtUtc: now,
                Outcome: "approval-required",
                Notes: request.Notes);
            var updatedMessage = _outbox.RecordAction(messageId, approvalExecution, "approval-required", "pending-approval");
            return new SpiderActionExecutionResult(
                MessageId: messageId,
                ActionId: actionId,
                Outcome: "approval-required",
                ApprovalState: "pending-approval",
                CardStatus: updatedMessage?.Card?.Status ?? "approval-required",
                UpdatedMessage: updatedMessage);
        }

        var auditEventId = $"{messageId}:{action.ActionId}:{now.ToUnixTimeMilliseconds()}";
        var auditEventType = string.IsNullOrWhiteSpace(action.AuditEventType)
            ? $"spider.action.{action.ActionId}"
            : action.AuditEventType;
        await _ledger.MergeEventsAsync(
            new[]
            {
                new SessionEventEnvelope(
                    request.SessionId,
                    request.SceneId,
                    auditEventType,
                    $"message:{messageId}|action:{action.ActionId}|semantic:{action.Semantic}|actor:{request.RequestedBy}|scene-revision:{request.SceneRevision}|notes:{request.Notes ?? string.Empty}",
                    now,
                    auditEventId,
                    request.SceneRevision,
                    auditEventId)
            },
            cancellationToken);

        var hiddenUntilUtc = action.ActionId switch
        {
            "snooze-2m" => now.AddMinutes(2),
            "mute-1m" => now.AddMinutes(1),
            _ => (DateTimeOffset?)null
        };
        var cardStatus = action.ActionId switch
        {
            "pin-card" => "pinned",
            "snooze-2m" => "snoozed",
            "mute-1m" => "muted",
            "bind-current-revision" => "bound",
            _ => "actioned"
        };

        var execution = new SpiderActionExecutionState(
            ActionId: action.ActionId,
            Status: "executed",
            PerformedBy: request.RequestedBy,
            ExecutedAtUtc: now,
            Outcome: "executed",
            AuditEventId: auditEventId,
            Notes: request.Notes);
        var updated = _outbox.RecordAction(messageId, execution, cardStatus, "approved", hiddenUntilUtc);
        var followUp = action.DeliveryBehavior == "queue-follow-up"
            ? _outbox.Enqueue(BuildFollowUpRequest(message, action, request, now))
            : null;

        return new SpiderActionExecutionResult(
            MessageId: messageId,
            ActionId: actionId,
            Outcome: "executed",
            ApprovalState: "approved",
            CardStatus: updated?.Card?.Status ?? cardStatus,
            AuditEventId: auditEventId,
            UpdatedMessage: updated,
            FollowUpMessage: followUp);
    }

    private static DeliveryOutboxCreateRequest BuildFollowUpRequest(
        DeliveryOutboxMessage message,
        SpiderTacticalAction action,
        SpiderActionExecuteRequest request,
        DateTimeOffset now)
    {
        var title = action.ActionId switch
        {
            "prep-matrix-exit" => "Matrix exit prepared",
            "reveal-threat" => "Threat reveal queued",
            _ => $"{action.Label} queued"
        };
        var cardKind = action.ActionId switch
        {
            "prep-matrix-exit" => "ops-task",
            "reveal-threat" => "player-reveal",
            _ => "follow-up"
        };
        var summary = action.ActionId switch
        {
            "prep-matrix-exit" => $"Spider queued a matrix disengage prep task for {message.SceneRevision}.",
            "reveal-threat" => "Spider queued a player-safe threat reveal for approval-aware delivery.",
            _ => action.Effect
        };

        return new DeliveryOutboxCreateRequest(
            SessionId: message.SessionId,
            SceneId: message.SceneId,
            SceneRevision: message.SceneRevision,
            Channel: message.Channel,
            Content: $"{title}: {summary} | sourceMessage={message.Id} | requestedBy={request.RequestedBy}",
            ApprovalState: action.RequiresApproval ? "approved" : "approved",
            AutonomyMode: message.AutonomyMode,
            Ttl: TimeSpan.FromMinutes(8),
            SceneStartedAtUtc: now,
            ProjectionFingerprint: message.ProjectionFingerprint,
            CollaborationMode: message.CollaborationMode,
            Card: new SpiderTacticalCard(
                CardId: Guid.NewGuid().ToString("N"),
                SessionId: message.SessionId,
                SceneId: message.SceneId,
                SceneRevision: message.SceneRevision,
                CardKind: cardKind,
                Title: title,
                Summary: summary,
                InterruptionLevel: Enum.TryParse<InterruptionLevel>(message.AutonomyMode, true, out var level)
                    ? level
                    : InterruptionLevel.Tactical,
                Status: "queued",
                ProjectionFingerprint: message.ProjectionFingerprint,
                Tags: MergeTags(message.Card?.Tags, action.ActionId),
                Actions: Array.Empty<SpiderTacticalAction>(),
                Evidence: new[]
                {
                    new EvidencePointer("spider-action", $"{message.Id}:{action.ActionId}", $"{action.Label} follow-up", "spider-action-service")
                },
                ActionExecutions: Array.Empty<SpiderActionExecutionState>(),
                CreatedAtUtc: now,
                StaleAfterUtc: now.AddMinutes(8),
                Payload: new SpiderTacticalPayload(
                    Workflow: "ooda",
                    Observe: $"action:{action.ActionId}",
                    Orient: message.Card?.Title ?? "spider-action",
                    Decide: "queue-follow-up",
                    Act: action.ActionId,
                    DecisionTier: "action",
                    SignalConfidence: message.Card?.Payload?.SignalConfidence,
                    BudgetRemainingThisMinute: message.Card?.Payload?.BudgetRemainingThisMinute,
                    BudgetLimitPerMinute: message.Card?.Payload?.BudgetLimitPerMinute,
                    BudgetAllowed: true,
                    IsStaleDraft: false,
                    DraftState: "active")));
    }

    private static IReadOnlyList<string> MergeTags(IReadOnlyList<string>? existingTags, string actionId)
    {
        return (existingTags ?? Array.Empty<string>())
            .Concat(new[] { "action-follow-up", actionId })
            .Distinct(StringComparer.Ordinal)
            .OrderBy(item => item, StringComparer.Ordinal)
            .ToArray();
    }
}
