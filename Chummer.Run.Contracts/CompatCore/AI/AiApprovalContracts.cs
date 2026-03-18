namespace Chummer.Contracts.AI;

public static class AiApprovalApiOperations
{
    public const string ListApprovals = "list-approvals";
    public const string SubmitApproval = "submit-approval";
    public const string ResolveApproval = "resolve-approval";
}

public static class AiApprovalStates
{
    public const string Draft = "draft";
    public const string PendingReview = "pending-review";
    public const string ApprovedPrivate = "approved-private";
    public const string ApprovedCanonical = "approved-canonical";
    public const string Rejected = "rejected";
    public const string Published = "published";
}

public static class AiApprovalTargetKinds
{
    public const string MediaJob = "media-job";
    public const string RecapDraft = "recap-draft";
    public const string CharacterActionDraft = "character-action-draft";
    public const string HubPublication = "hub-publication";
}

public static class AiApprovalDecisionKinds
{
    public const string Approve = "approve";
    public const string Reject = "reject";
}

public sealed record AiApprovalQuery(
    string? State = null,
    string? TargetKind = null,
    int MaxCount = 20);

public sealed record AiApprovalSubmitRequest(
    string TargetKind,
    string TargetId,
    string Title,
    string Summary,
    string RequestedState = AiApprovalStates.PendingReview,
    string? ReviewerScopeHint = null);

public sealed record AiApprovalResolveRequest(
    string Decision,
    string? Comment = null,
    string? FinalState = null);

public sealed record AiApprovalProjection(
    string ApprovalId,
    string TargetKind,
    string TargetId,
    string Title,
    string Summary,
    string State,
    string RequestedByOwnerId,
    DateTimeOffset CreatedAtUtc,
    string? ReviewerScopeHint = null,
    string? Decision = null,
    string? ResolvedByOwnerId = null,
    DateTimeOffset? ResolvedAtUtc = null);

public sealed record AiApprovalCatalog(
    IReadOnlyList<AiApprovalProjection> Items,
    int TotalCount);

public sealed record AiApprovalReceipt(
    string ApprovalId,
    string State,
    string Message,
    bool ExternalBrokerConfigured = false,
    string? TargetKind = null,
    string? TargetId = null,
    string? OwnerId = null);
