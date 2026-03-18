using System.Collections.Generic;
using System.Linq;
using Chummer.Contracts.Presentation;

namespace Chummer.Contracts.Hub;

public static class HubCatalogItemKinds
{
    public const string RulePack = "rulepack";
    public const string RuleProfile = "ruleprofile";
    public const string BuildKit = "buildkit";
    public const string NpcEntry = "npc-entry";
    public const string NpcPack = "npc-pack";
    public const string EncounterPack = "encounter-pack";
    public const string RuntimeLock = "runtime-lock";

    public static IReadOnlyList<string> All { get; } =
    [
        RulePack,
        RuleProfile,
        BuildKit,
        NpcEntry,
        NpcPack,
        EncounterPack,
        RuntimeLock
    ];

    public static bool IsDefined(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        string normalized = value.Trim().ToLowerInvariant();
        return All.Contains(normalized, StringComparer.Ordinal);
    }

    public static string NormalizeRequired(string value, string? paramName = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(value, paramName);

        string normalized = value.Trim().ToLowerInvariant();
        if (All.Contains(normalized, StringComparer.Ordinal))
        {
            return normalized;
        }

        throw new ArgumentOutOfRangeException(paramName ?? nameof(value), $"Unsupported hub project kind '{value}'.");
    }

    public static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? null
            : NormalizeRequired(value);
}

public static class HubCatalogFacetIds
{
    public const string Kind = "kind";
    public const string Ruleset = "ruleset";
    public const string Visibility = "visibility";
    public const string Trust = "trust";
}

public static class HubCatalogSortIds
{
    public const string Title = "title";
    public const string Kind = "kind";
    public const string Ruleset = "ruleset";
}

public sealed record HubCatalogItem(
    string ItemId,
    string Kind,
    string Title,
    string Description,
    string RulesetId,
    string Visibility,
    string TrustTier,
    string LinkTarget,
    string? Version = null,
    bool Installable = true,
    string? InstallState = null,
    HubReviewSummary? OwnerReview = null,
    HubReviewAggregateSummary? AggregateReview = null,
    HubPublisherSummary? Publisher = null);

public sealed record HubCatalogResultPage(
    BrowseQuery Query,
    IReadOnlyList<HubCatalogItem> Items,
    IReadOnlyList<FacetDefinition> Facets,
    IReadOnlyList<SortDefinition> Sorts,
    int TotalCount);
