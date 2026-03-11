namespace Chummer.Run.AI.Compatibility;

[Obsolete("Use Chummer.Run.Contracts.Spider.InterruptionLevel.")]
internal enum InterruptionLevel
{
    Off,
    Low,
    Tactical,
    Narrative,
    High
}

[Obsolete("Use Chummer.Run.Contracts.Spider.SpiderObservation.")]
internal sealed record SpiderObservation(
    string SessionId,
    string Source,
    string Payload,
    DateTimeOffset ObservedAtUtc,
    string? SceneId = null,
    string? SceneRevision = null);

[Obsolete("Use Chummer.Run.Contracts.Spider.FastSignal.")]
internal sealed record FastSignal(
    string SessionId,
    string Signal,
    int Confidence,
    bool Escalate);

[Obsolete("Use Chummer.Run.Contracts.Spider.SpiderDeepAnalysis.")]
internal sealed record SpiderDeepAnalysis(
    string SessionId,
    string SceneId,
    string SceneRevision,
    string Summary,
    string RecommendedCardKind,
    string RecommendedCardTitle,
    InterruptionLevel RecommendedInterruptionLevel,
    IReadOnlyList<string> Tags,
    IReadOnlyList<SpiderTacticalAction> SuggestedActions,
    IReadOnlyList<EvidencePointer> Evidence,
    ProviderRouteDecision RouteDecision,
    PromptLineage? PromptLineage = null,
    string? ProviderOutput = null,
    IReadOnlyList<string>? FocusEventTypes = null);

[Obsolete("Use Chummer.Run.Contracts.Spider.EvidencePointer.")]
internal sealed record EvidencePointer(
    string Kind,
    string Reference,
    string Label,
    string? Source = null);

[Obsolete("Use Chummer.Run.Contracts.Spider.SpiderTacticalAction.")]
internal sealed record SpiderTacticalAction(
    string ActionId,
    string Label,
    string Effect,
    string Semantic = "note",
    bool RequiresApproval = false,
    string DeliveryBehavior = "annotate",
    string? AuditEventType = null);

[Obsolete("Use Chummer.Run.Contracts.Spider.SpiderActionExecutionState.")]
internal sealed record SpiderActionExecutionState(
    string ActionId,
    string Status,
    string PerformedBy,
    DateTimeOffset ExecutedAtUtc,
    string Outcome,
    string? AuditEventId = null,
    string? Notes = null);

[Obsolete("Use Chummer.Run.Contracts.Spider.SpiderTacticalPayload.")]
internal sealed record SpiderTacticalPayload(
    string Workflow = "ooda",
    string Observe = "",
    string Orient = "",
    string Decide = "",
    string Act = "",
    string DecisionTier = "fast",
    int? SignalConfidence = null,
    int? BudgetRemainingThisMinute = null,
    int? BudgetLimitPerMinute = null,
    bool BudgetAllowed = true,
    bool IsStaleDraft = false,
    string DraftState = "active");

[Obsolete("Use Chummer.Run.Contracts.Spider.PolicyDecision.")]
internal sealed record PolicyDecision(
    string SessionId,
    string Action,
    InterruptionLevel InterruptionLevel,
    string Rationale,
    bool ShouldDeliver,
    TimeSpan? ExpireAfter = null,
    string CardKind = "note",
    string CardTitle = "",
    IReadOnlyList<string>? Tags = null,
    IReadOnlyList<SpiderTacticalAction>? SuggestedActions = null,
    IReadOnlyList<EvidencePointer>? Evidence = null,
    string DecisionTier = "fast",
    SpiderDeepAnalysis? DeepAnalysis = null);

[Obsolete("Use Chummer.Run.Contracts.Spider.SpiderTacticalCard.")]
internal sealed record SpiderTacticalCard(
    string CardId,
    string SessionId,
    string SceneId,
    string SceneRevision,
    string CardKind,
    string Title,
    string Summary,
    InterruptionLevel InterruptionLevel,
    string Status,
    string ProjectionFingerprint,
    IReadOnlyList<string> Tags,
    IReadOnlyList<SpiderTacticalAction> Actions,
    IReadOnlyList<EvidencePointer> Evidence,
    DateTimeOffset CreatedAtUtc,
    IReadOnlyList<SpiderActionExecutionState>? ActionExecutions = null,
    DateTimeOffset? StaleAfterUtc = null,
    SpiderTacticalPayload? Payload = null);

[Obsolete("Use Chummer.Run.Contracts.Spider.DeliveryOutboxMessage.")]
internal sealed record DeliveryOutboxMessage(
    string Id,
    string SessionId,
    string SceneId,
    string SceneRevision,
    string Channel,
    string ApprovalState,
    string AutonomyMode,
    string Content,
    DateTimeOffset EnqueuedAtUtc,
    TimeSpan? StaleAfter = null,
    DateTimeOffset? HiddenUntilUtc = null,
    string ProjectionFingerprint = "empty",
    string CollaborationMode = "local-first",
    SpiderTacticalCard? Card = null);

[Obsolete("Use Chummer.Run.Contracts.Spider.DeliveryOutboxCreateRequest.")]
internal sealed record DeliveryOutboxCreateRequest(
    string SessionId,
    string SceneId,
    string SceneRevision,
    string Channel,
    string Content,
    string ApprovalState,
    string AutonomyMode,
    TimeSpan? Ttl = null,
    DateTimeOffset? SceneStartedAtUtc = null,
    DateTimeOffset? HiddenUntilUtc = null,
    string ProjectionFingerprint = "empty",
    string CollaborationMode = "local-first",
    SpiderTacticalCard? Card = null);

[Obsolete("Use Chummer.Run.Contracts.Spider.SpiderActionExecuteRequest.")]
internal sealed record SpiderActionExecuteRequest(
    string SessionId,
    string SceneId,
    string SceneRevision,
    string RequestedBy,
    string? ApprovalState = null,
    string? Notes = null);

[Obsolete("Use Chummer.Run.Contracts.Spider.SpiderActionExecutionResult.")]
internal sealed record SpiderActionExecutionResult(
    string MessageId,
    string ActionId,
    string Outcome,
    string ApprovalState,
    string CardStatus,
    string? AuditEventId = null,
    DeliveryOutboxMessage? UpdatedMessage = null,
    DeliveryOutboxMessage? FollowUpMessage = null);
