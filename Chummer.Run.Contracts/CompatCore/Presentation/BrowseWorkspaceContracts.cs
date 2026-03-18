namespace Chummer.Contracts.Presentation;

public static class BrowseWorkspaceSurfaceIds
{
    public const string BrowseWorkspace = "browse-workspace";
    public const string SelectionDialog = "selection-dialog";
    public const string FacetPanel = "facet-panel";
    public const string ResultGrid = "result-grid";
    public const string DetailPane = "detail-pane";
    public const string SelectionSummary = "selection-summary";
}

public static class BrowseWorkspaceSectionKinds
{
    public const string Query = "query";
    public const string Facets = "facets";
    public const string Results = "results";
    public const string Detail = "detail";
    public const string Selection = "selection";
}

public static class SelectionDialogModes
{
    public const string SingleSelect = "single-select";
    public const string MultiSelect = "multi-select";
    public const string PreviewRequired = "preview-required";
}

public sealed record BrowseWorkspaceSection(
    string SectionId,
    string Kind,
    string Title,
    bool IsVisible = true);

public sealed record BrowseItemDetail(
    string ItemId,
    string Title,
    IReadOnlyList<string> SummaryLines,
    string? ExplainEntryId = null,
    string? DisableReasonId = null);

public sealed record SelectionSummaryItem(
    string ItemId,
    string Title,
    string? Detail = null,
    string? DisableReasonId = null);

public sealed record BrowseWorkspaceProjection(
    string WorkspaceId,
    string WorkflowId,
    BrowseResultPage Results,
    IReadOnlyList<BrowseWorkspaceSection> Sections,
    IReadOnlyList<SelectionSummaryItem> SelectedItems,
    BrowseItemDetail? ActiveDetail = null,
    string? ActiveSurfaceId = null);

public sealed record SelectionDialogProjection(
    string DialogId,
    string Title,
    string Mode,
    BrowseWorkspaceProjection Workspace,
    bool CanConfirm,
    string ConfirmActionId,
    string CancelActionId);
