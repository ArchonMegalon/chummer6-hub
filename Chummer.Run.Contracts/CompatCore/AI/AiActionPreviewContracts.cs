namespace Chummer.Contracts.AI;

public static class AiActionPreviewApiOperations
{
    public const string PreviewKarmaSpend = "preview-karma-spend";
    public const string PreviewNuyenSpend = "preview-nuyen-spend";
    public const string CreateApplyPreview = "create-apply-preview";
}

public static class AiActionPreviewKinds
{
    public const string KarmaSpend = "karma-spend";
    public const string NuyenSpend = "nuyen-spend";
    public const string ApplyPreview = "apply-preview";
}

public static class AiActionPreviewStates
{
    public const string Scaffolded = "scaffolded";
    public const string Blocked = "blocked";
}

public sealed record AiSpendPlanStep(
    string StepId,
    string Title,
    decimal? Amount = null,
    string? TargetId = null,
    string? Notes = null);

public sealed record AiSpendPlanPreviewRequest(
    string CharacterId,
    string RuntimeFingerprint,
    IReadOnlyList<AiSpendPlanStep> Steps,
    string? Goal = null,
    string? WorkspaceId = null);

public sealed record AiApplyPreviewRequest(
    string CharacterId,
    string RuntimeFingerprint,
    AiActionDraft ActionDraft,
    string? Goal = null,
    string? WorkspaceId = null);

public sealed record AiActionPreviewReceipt(
    string PreviewId,
    string Operation,
    string PreviewKind,
    string CharacterId,
    string CharacterDisplayName,
    string RulesetId,
    string RuntimeFingerprint,
    string State,
    string Summary,
    int StepCount,
    decimal? TotalRequested,
    string? Unit,
    IReadOnlyList<string> PreparedEffects,
    IReadOnlyList<AiEvidenceEntry> Evidence,
    IReadOnlyList<AiRiskEntry> Risks,
    bool RequiresConfirmation = true,
    string? ProfileId = null,
    string? ProfileTitle = null,
    string? WorkspaceId = null);
