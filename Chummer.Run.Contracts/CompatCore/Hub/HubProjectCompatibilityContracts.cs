using Chummer.Contracts.Rulesets;

namespace Chummer.Contracts.Hub;

public static class HubProjectCompatibilityRowKinds
{
    public const string Ruleset = "ruleset";
    public const string EngineApi = "engine-api";
    public const string Visibility = "visibility";
    public const string Trust = "trust";
    public const string InstallState = "install-state";
    public const string Capabilities = "capabilities";
    public const string SessionRuntime = "session-runtime";
    public const string HostedPublic = "hosted-public";
    public const string RuntimeFingerprint = "runtime-fingerprint";
    public const string RuntimeRequirements = "runtime-requirements";
}

public static class HubProjectCompatibilityStates
{
    public const string Compatible = "compatible";
    public const string ReviewRequired = "review-required";
    public const string Blocked = "blocked";
    public const string Informational = "informational";
}

public sealed record HubProjectCompatibilityRow(
    string Kind,
    string Label,
    string State,
    string CurrentValue,
    string? RequiredValue = null,
    string? Notes = null,
    string? LabelKey = null,
    IReadOnlyList<RulesetExplainParameter>? LabelParameters = null,
    string? CurrentValueKey = null,
    IReadOnlyList<RulesetExplainParameter>? CurrentValueParameters = null,
    string? RequiredValueKey = null,
    IReadOnlyList<RulesetExplainParameter>? RequiredValueParameters = null,
    string? NotesKey = null,
    IReadOnlyList<RulesetExplainParameter>? NotesParameters = null);

public sealed record HubProjectCompatibilityMatrix(
    string Kind,
    string ItemId,
    IReadOnlyList<HubProjectCompatibilityRow> Rows,
    DateTimeOffset GeneratedAtUtc,
    IReadOnlyList<HubProjectCapabilityDescriptorProjection>? Capabilities = null);

public static class HubProjectCompatibilityContractLocalization
{
    public static string ResolveLabelKey(HubProjectCompatibilityRow row)
    {
        ArgumentNullException.ThrowIfNull(row);

        return string.IsNullOrWhiteSpace(row.LabelKey)
            ? row.Label
            : row.LabelKey;
    }

    public static IReadOnlyList<RulesetExplainParameter> ResolveLabelParameters(HubProjectCompatibilityRow row)
    {
        ArgumentNullException.ThrowIfNull(row);
        return row.LabelParameters ?? [];
    }

    public static string ResolveCurrentValueKey(HubProjectCompatibilityRow row)
    {
        ArgumentNullException.ThrowIfNull(row);

        return string.IsNullOrWhiteSpace(row.CurrentValueKey)
            ? row.CurrentValue
            : row.CurrentValueKey;
    }

    public static IReadOnlyList<RulesetExplainParameter> ResolveCurrentValueParameters(HubProjectCompatibilityRow row)
    {
        ArgumentNullException.ThrowIfNull(row);
        return row.CurrentValueParameters ?? [];
    }

    public static string? ResolveRequiredValueKey(HubProjectCompatibilityRow row)
    {
        ArgumentNullException.ThrowIfNull(row);

        return string.IsNullOrWhiteSpace(row.RequiredValueKey)
            ? row.RequiredValue
            : row.RequiredValueKey;
    }

    public static IReadOnlyList<RulesetExplainParameter> ResolveRequiredValueParameters(HubProjectCompatibilityRow row)
    {
        ArgumentNullException.ThrowIfNull(row);
        return row.RequiredValueParameters ?? [];
    }

    public static string? ResolveNotesKey(HubProjectCompatibilityRow row)
    {
        ArgumentNullException.ThrowIfNull(row);

        return string.IsNullOrWhiteSpace(row.NotesKey)
            ? row.Notes
            : row.NotesKey;
    }

    public static IReadOnlyList<RulesetExplainParameter> ResolveNotesParameters(HubProjectCompatibilityRow row)
    {
        ArgumentNullException.ThrowIfNull(row);
        return row.NotesParameters ?? [];
    }
}
