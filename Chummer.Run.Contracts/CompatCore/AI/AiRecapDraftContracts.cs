namespace Chummer.Contracts.AI;

public static class AiRecapDraftApiOperations
{
    public const string ListRecapDrafts = "list-recap-drafts";
    public const string CreateRecapDraft = "create-recap-draft";
}

public static class AiRecapDraftStates
{
    public const string Draft = "draft";
    public const string PendingApproval = "pending-approval";
    public const string Approved = "approved";
    public const string Rejected = "rejected";
}

public sealed record AiRecapDraftQuery(
    string? SessionId = null,
    int MaxCount = 20);

public sealed record AiRecapDraftRequest(
    string SourceKind,
    string SourceId,
    string Title,
    string? SessionId = null,
    string? CampaignId = null);

public sealed record AiRecapDraftProjection(
    string DraftId,
    string SourceKind,
    string SourceId,
    string Title,
    string State,
    DateTimeOffset CreatedAtUtc,
    string? SessionId = null,
    string? CampaignId = null);

public sealed record AiRecapDraftCatalog(
    IReadOnlyList<AiRecapDraftProjection> Items,
    int TotalCount);

public sealed record AiRecapDraftReceipt(
    string DraftId,
    string State,
    string Message,
    bool ApprovalRequired = true,
    string? SessionId = null,
    string? OwnerId = null);
