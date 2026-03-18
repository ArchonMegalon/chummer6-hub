namespace Chummer.Contracts.Presentation;

public static class BrowseFacetKinds
{
    public const string SingleSelect = "single-select";
    public const string MultiSelect = "multi-select";
    public const string Toggle = "toggle";
    public const string Range = "range";
}

public static class BrowseSortDirections
{
    public const string Ascending = "asc";
    public const string Descending = "desc";
}

public static class BrowseValueKinds
{
    public const string Text = "text";
    public const string Number = "number";
    public const string Tag = "tag";
    public const string Availability = "availability";
}

public sealed record BrowseQuery(
    string QueryText,
    IReadOnlyDictionary<string, IReadOnlyList<string>> FacetSelections,
    string SortId,
    string SortDirection = BrowseSortDirections.Ascending,
    int Offset = 0,
    int Limit = 50);

public sealed record FacetOptionDefinition(
    string Value,
    string Label,
    int Count = 0,
    bool Selected = false,
    string? DisableReasonId = null);

public sealed record FacetDefinition(
    string FacetId,
    string Label,
    string Kind,
    IReadOnlyList<FacetOptionDefinition> Options,
    bool MultiSelect = true);

public sealed record SortDefinition(
    string SortId,
    string Label,
    string Direction = BrowseSortDirections.Ascending,
    bool IsDefault = false);

public sealed record ViewPreset(
    string PresetId,
    string Label,
    BrowseQuery Query,
    bool Shared = false);

public sealed record DisableReason(
    string ReasonId,
    string Summary,
    string? ExplainEntryId = null,
    bool IsBlocking = true);

public sealed record BrowseColumnDefinition(
    string ColumnId,
    string Label,
    string ValueKind,
    bool IsPrimary = false,
    bool Sortable = true);

public sealed record BrowseResultItem(
    string ItemId,
    string Title,
    IReadOnlyDictionary<string, string> ColumnValues,
    IReadOnlyList<string> FacetValues,
    bool IsSelectable = true,
    string? DisableReasonId = null);

public sealed record BrowseResultPage(
    BrowseQuery Query,
    IReadOnlyList<BrowseResultItem> Items,
    IReadOnlyList<BrowseColumnDefinition> Columns,
    IReadOnlyList<FacetDefinition> Facets,
    IReadOnlyList<SortDefinition> Sorts,
    IReadOnlyList<ViewPreset> ViewPresets,
    IReadOnlyList<DisableReason> DisableReasons,
    int TotalCount,
    string? ContinuationToken = null);

public sealed record SelectionResult(
    string ItemId,
    string Title,
    IReadOnlyList<string> SelectedFacetValues,
    string? PresetId = null,
    string? DisableReasonId = null);
