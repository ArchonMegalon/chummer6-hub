namespace Chummer.Contracts.Hub;

public static class HubPublicationOperations
{
    public const string ListDrafts = "list-drafts";
    public const string CreateDraft = "create-draft";
    public const string UpdateDraft = "update-draft";
    public const string ArchiveDraft = "archive-draft";
    public const string DeleteDraft = "delete-draft";
    public const string SubmitProject = "submit-project";
    public const string ListModerationQueue = "list-moderation-queue";
    public const string ApproveModerationCase = "approve-moderation-case";
    public const string RejectModerationCase = "reject-moderation-case";
}

public static class HubPublicationStates
{
    public const string Draft = "draft";
    public const string Submitted = "submitted";
    public const string Archived = "archived";
    public const string PendingReview = "pending-review";
}

public static class HubModerationStates
{
    public const string PendingReview = "pending-review";
    public const string Approved = "approved";
    public const string Rejected = "rejected";
}

public sealed record HubPublishDraftRequest(
    string ProjectKind,
    string ProjectId,
    string RulesetId,
    string Title,
    string? Summary = null,
    string? Description = null,
    string? PublisherId = null);

public sealed record HubUpdateDraftRequest(
    string Title,
    string? Summary = null,
    string? Description = null,
    string? PublisherId = null);

public sealed record HubPublishDraftReceipt(
    string DraftId,
    string ProjectKind,
    string ProjectId,
    string RulesetId,
    string Title,
    string? Summary,
    string OwnerId,
    string? PublisherId,
    string State,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? SubmittedAtUtc = null);

public sealed record HubPublishDraftList(
    IReadOnlyList<HubPublishDraftReceipt> Items);

public sealed record HubDraftDetailProjection(
    HubPublishDraftReceipt Draft,
    HubModerationQueueItem? Moderation,
    string? Description = null,
    string? LatestModerationNotes = null,
    DateTimeOffset? LatestModerationUpdatedAtUtc = null);

public sealed record HubSubmitProjectRequest(
    string? Notes = null,
    string? PublisherId = null);

public sealed record HubProjectSubmissionReceipt(
    string DraftId,
    string CaseId,
    string ProjectKind,
    string ProjectId,
    string RulesetId,
    string OwnerId,
    string? PublisherId,
    string State,
    string ReviewState,
    string? Notes = null,
    DateTimeOffset? SubmittedAtUtc = null);

public sealed record HubModerationQueueItem(
    string CaseId,
    string DraftId,
    string ProjectKind,
    string ProjectId,
    string RulesetId,
    string Title,
    string OwnerId,
    string? PublisherId,
    string State,
    DateTimeOffset CreatedAtUtc,
    string? Summary = null);

public sealed record HubModerationQueue(
    IReadOnlyList<HubModerationQueueItem> Items);

public sealed record HubModerationDecisionRequest(
    string? Notes = null);

public sealed record HubModerationDecisionReceipt(
    string CaseId,
    string DraftId,
    string ProjectKind,
    string ProjectId,
    string RulesetId,
    string OwnerId,
    string? PublisherId,
    string State,
    string? Notes,
    DateTimeOffset UpdatedAtUtc);

public sealed record HubDraftRecord(
    string DraftId,
    string ProjectKind,
    string ProjectId,
    string RulesetId,
    string Title,
    string OwnerId,
    string? PublisherId,
    string State,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? SubmittedAtUtc = null,
    string? Summary = null,
    string? Description = null);

public sealed record HubModerationCaseRecord(
    string CaseId,
    string DraftId,
    string ProjectKind,
    string ProjectId,
    string RulesetId,
    string Title,
    string OwnerId,
    string? PublisherId,
    string State,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    string? Summary = null,
    string? Notes = null);

public sealed record HubPublicationNotImplementedReceipt(
    string Error,
    string Operation,
    string Message,
    string? ProjectKind = null,
    string? ProjectId = null,
    string? OwnerId = null);

public sealed record HubPublicationResult<T>(
    T? Payload = default,
    HubPublicationNotImplementedReceipt? NotImplemented = null)
{
    public bool IsImplemented => NotImplemented is null;

    public static HubPublicationResult<T> Implemented(T payload)
        => new(payload, null);

    public static HubPublicationResult<T> FromNotImplemented(HubPublicationNotImplementedReceipt receipt)
        => new(default, receipt);
}
