using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.Contracts.Heyy;

public sealed record HeyyScamChatIngestRequest(
    [Required(AllowEmptyStrings = false), StringLength(64)] string Channel,
    [StringLength(128)] string? ConversationId,
    [StringLength(128)] string? CounterpartyHandle,
    [Required(AllowEmptyStrings = false), StringLength(4096)] string MessageText,
    DateTimeOffset? ReceivedAtUtc = null,
    [StringLength(160)] string? Source = null);

public sealed record HeyyScamChatDraftResponse(
    string ConversationId,
    string Mode,
    bool ManualApprovalRequired,
    bool AutoSendAllowed,
    string PersonaId,
    string DraftText,
    string PacingHint,
    int MinimumDelaySeconds,
    HeyyScamChatEnrichmentResponse Enrichment,
    string SafetySummary,
    string Status,
    string? FailureReason);

public sealed record HeyyScamChatConversationResponse(
    string ConversationId,
    string Channel,
    string CounterpartyMasked,
    string Mode,
    string PersonaId,
    string SafetyStatus,
    HeyyScamChatEnrichmentResponse Enrichment,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    IReadOnlyList<HeyyScamChatMessageResponse> Messages,
    HeyyScamChatDraftResponse? LatestDraft,
    IReadOnlyList<HeyyScamChatApprovalResponse> Approvals,
    IReadOnlyList<HeyyScamChatOperatorSummaryResponse> OperatorSummaries);

public sealed record HeyyScamChatMessageResponse(
    string MessageId,
    string Direction,
    string Text,
    string SafetyLabel,
    string PacingHint,
    DateTimeOffset CreatedAtUtc);

public sealed record HeyyScamChatDigestRequest(
    DateOnly? Date = null,
    bool DryRun = false);

public sealed record HeyyScamChatApproveDraftRequest(
    [StringLength(4096)] string? ApprovedText = null,
    [StringLength(128)] string? OperatorId = null,
    [StringLength(64)] string DeliveryMode = "manual_copy",
    [StringLength(160)] string? Recipient = null,
    bool ConfirmManualApproval = false,
    bool DryRun = true,
    [StringLength(160)] string? IdempotencyKey = null);

public sealed record HeyyScamChatApprovalResponse(
    string ApprovalId,
    string ConversationId,
    string? DraftId,
    string DeliveryMode,
    string Status,
    bool DryRun,
    bool ManualApprovalConfirmed,
    bool AutoSendAllowed,
    string OperatorId,
    string RecipientMasked,
    string ApprovedText,
    string PacingHint,
    string? DeliveryRef,
    string? FailureReason,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset AttemptedAtUtc,
    string IdempotencyKey);

public sealed record HeyyScamChatOperatorSummaryResponse(
    string SummaryId,
    string ConversationId,
    int IncomingTurnCount,
    int Threshold,
    string Status,
    string Channel,
    string RecipientMasked,
    string Content,
    string? DeliveryRef,
    string? FailureReason,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset AttemptedAtUtc,
    string EventKey);

public sealed record HeyyScamChatDigestResponse(
    string DigestId,
    DateOnly Date,
    string Status,
    int ConversationCount,
    int MessageCount,
    bool DryRun,
    string? DeliveryRef,
    string? FailureReason,
    string Content);

public sealed record HeyyScamChatEnrichmentResponse(
    string ScamPattern,
    string ReplyObjective,
    string OperatorNextAction,
    IReadOnlyList<string> RiskSignals,
    IReadOnlyList<string> MissingContextChecks,
    IReadOnlyList<string> ForbiddenActions,
    int SuggestedDelaySeconds);
