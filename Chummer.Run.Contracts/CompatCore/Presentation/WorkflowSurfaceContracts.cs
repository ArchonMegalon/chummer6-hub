namespace Chummer.Contracts.Presentation;

public static class ShellRegionIds
{
    public const string MenuBar = "MenuBar";
    public const string ToolStrip = "ToolStrip";
    public const string MdiStrip = "MdiStrip";
    public const string WorkspaceLeftPane = "WorkspaceLeftPane";
    public const string SummaryHeader = "SummaryHeader";
    public const string MetadataPanel = "MetadataPanel";
    public const string SectionPane = "SectionPane";
    public const string ImportPanel = "ImportPanel";
    public const string CommandPanel = "CommandPanel";
    public const string ResultPanel = "ResultPanel";
    public const string DialogHost = "DialogHost";
    public const string StatusStrip = "StatusStrip";
}

public static class WorkflowDefinitionIds
{
    public const string LibraryShell = "LibraryShell";
    public const string CreateWorkbench = "CreateWorkbench";
    public const string CareerWorkbench = "CareerWorkbench";
    public const string SelectionDialog = "SelectionDialog";
    public const string EntityEditor = "EntityEditor";
    public const string ExpenseLedger = "ExpenseLedger";
    public const string HistoryTimeline = "HistoryTimeline";
    public const string DiceTool = "DiceTool";
    public const string ExportTool = "ExportTool";
    public const string PackManager = "PackManager";
    public const string SessionDashboard = "SessionDashboard";
}

public static class WorkflowSurfaceKinds
{
    public const string ShellRegion = "shell-region";
    public const string Workbench = "workbench";
    public const string Dialog = "dialog";
    public const string Tool = "tool";
    public const string Dashboard = "dashboard";
}

public static class WorkflowLayoutTokens
{
    public const string ShellFrame = "shell-frame";
    public const string CreateWizard = "create-wizard";
    public const string CareerWorkbench = "career-workbench";
    public const string SelectionDialog = "selection-dialog";
    public const string EntityEditor = "entity-editor";
    public const string Ledger = "ledger";
    public const string Timeline = "timeline";
    public const string ToolPanel = "tool-panel";
    public const string SessionDashboard = "session-dashboard";
}

public sealed record WorkflowDefinition(
    string WorkflowId,
    string Title,
    IReadOnlyList<string> SurfaceIds,
    bool RequiresOpenWorkspace,
    bool MobileOptimized = false);

public sealed record WorkflowSurfaceDefinition(
    string SurfaceId,
    string WorkflowId,
    string Kind,
    string RegionId,
    string LayoutToken,
    IReadOnlyList<string> ActionIds,
    IReadOnlyDictionary<string, string>? RendererHints = null);
