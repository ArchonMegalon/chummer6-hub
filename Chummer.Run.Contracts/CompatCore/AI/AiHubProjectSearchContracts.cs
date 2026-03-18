using Chummer.Contracts.Rulesets;

namespace Chummer.Contracts.AI;

public static class AiHubProjectSearchApiOperations
{
    public const string SearchProjects = "search-hub-projects";
    public const string GetProjectDetail = "get-hub-project-detail";
}

public sealed record AiHubProjectSearchQuery(
    string QueryText,
    string? Type = null,
    string? RulesetId = null,
    int MaxCount = 10);

public sealed record AiHubProjectProjection(
    string ProjectId,
    string Kind,
    string Title,
    string Description,
    string RulesetId,
    string Visibility,
    string TrustTier,
    string? Version = null,
    bool Installable = true,
    string? InstallState = null,
    string? Publisher = null);

public sealed record AiHubProjectCatalog(
    IReadOnlyList<AiHubProjectProjection> Items,
    int TotalCount);

public sealed record AiHubProjectFact(
    string Label,
    string Value);

public sealed record AiHubProjectDependencyProjection(
    string Kind,
    string ItemKind,
    string ItemId,
    string Version,
    string? Notes = null);

public sealed record AiHubProjectActionProjection(
    string ActionId,
    string Label,
    string Kind,
    bool Enabled = true,
    string? DisabledReasonKey = null,
    IReadOnlyList<RulesetExplainParameter>? DisabledReasonParameters = null,
    string? DisabledReason = null);

public sealed record AiHubProjectDetailProjection(
    AiHubProjectProjection Summary,
    string? RuntimeFingerprint,
    IReadOnlyList<AiHubProjectFact> Facts,
    IReadOnlyList<AiHubProjectDependencyProjection> Dependencies,
    IReadOnlyList<AiHubProjectActionProjection> Actions);

public static class AiHubProjectSearchContractLocalization
{
    public static string? ResolveDisabledReasonKey(AiHubProjectActionProjection action)
    {
        ArgumentNullException.ThrowIfNull(action);

        return string.IsNullOrWhiteSpace(action.DisabledReasonKey)
            ? action.DisabledReason
            : action.DisabledReasonKey;
    }

    public static IReadOnlyList<RulesetExplainParameter> ResolveDisabledReasonParameters(AiHubProjectActionProjection action)
    {
        ArgumentNullException.ThrowIfNull(action);
        return action.DisabledReasonParameters ?? [];
    }
}
