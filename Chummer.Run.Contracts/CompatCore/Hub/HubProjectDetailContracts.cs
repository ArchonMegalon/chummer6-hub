using Chummer.Contracts.Rulesets;

namespace Chummer.Contracts.Hub;

public static class HubProjectDependencyKinds
{
    public const string DependsOn = "depends-on";
    public const string ConflictsWith = "conflicts-with";
    public const string IncludesRulePack = "includes-rulepack";
    public const string IncludesNpcEntry = "includes-npc-entry";
    public const string RequiresRulePack = "requires-rulepack";
    public const string RequiresRuntimeFingerprint = "requires-runtime-fingerprint";
}

public static class HubProjectActionKinds
{
    public const string Install = "install";
    public const string Apply = "apply";
    public const string PreviewRuntime = "preview-runtime";
    public const string InspectRuntime = "inspect-runtime";
    public const string OpenRegistry = "open-registry";
    public const string CloneToLibrary = "clone-to-library";
}

public sealed record HubProjectDetailFact(
    string FactId,
    string Label,
    string Value);

public sealed record HubProjectDependency(
    string Kind,
    string ItemKind,
    string ItemId,
    string Version,
    string? Notes = null);

public sealed record HubProjectAction(
    string ActionId,
    string Label,
    string Kind,
    string? LinkTarget = null,
    bool Enabled = true,
    string? DisabledReasonKey = null,
    IReadOnlyList<RulesetExplainParameter>? DisabledReasonParameters = null,
    string? DisabledReason = null);

public sealed record HubProjectCapabilityDescriptorProjection(
    string CapabilityId,
    string? InvocationKind,
    string? Title,
    bool Explainable,
    bool SessionSafe,
    RulesetGasBudget? DefaultGasBudget = null,
    RulesetGasBudget? MaximumGasBudget = null,
    string? ProviderId = null,
    string? PackId = null,
    string? AssetKind = null,
    string? AssetMode = null,
    string? TitleKey = null,
    IReadOnlyList<RulesetExplainParameter>? TitleParameters = null);

public sealed record HubProjectDetailProjection(
    HubCatalogItem Summary,
    string? OwnerId,
    string? CatalogKind,
    string? PublicationStatus,
    string? ReviewState,
    string? RuntimeFingerprint,
    HubReviewSummary? OwnerReview,
    HubReviewAggregateSummary? AggregateReview,
    IReadOnlyList<HubProjectDetailFact> Facts,
    IReadOnlyList<HubProjectDependency> Dependencies,
    IReadOnlyList<HubProjectAction> Actions,
    IReadOnlyList<HubProjectCapabilityDescriptorProjection>? Capabilities = null,
    HubPublisherSummary? Publisher = null);

public static class HubProjectDetailContractLocalization
{
    public static string? ResolveDisabledReasonKey(HubProjectAction action)
    {
        ArgumentNullException.ThrowIfNull(action);

        return string.IsNullOrWhiteSpace(action.DisabledReasonKey)
            ? action.DisabledReason
            : action.DisabledReasonKey;
    }

    public static IReadOnlyList<RulesetExplainParameter> ResolveDisabledReasonParameters(HubProjectAction action)
    {
        ArgumentNullException.ThrowIfNull(action);
        return action.DisabledReasonParameters ?? [];
    }
}
