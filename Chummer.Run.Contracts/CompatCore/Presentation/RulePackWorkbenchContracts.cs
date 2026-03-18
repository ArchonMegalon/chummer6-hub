using Chummer.Contracts.Content;

namespace Chummer.Contracts.Presentation;

public static class RulePackWorkbenchSurfaceIds
{
    public const string Library = "rulepack-library";
    public const string Inspector = "rulepack-inspector";
    public const string DependencyGraph = "dependency-graph-view";
    public const string ValidationPanel = "validation-panel";
    public const string OverrideEditor = "override-editor";
}

public static class RulePackInstallStates
{
    public const string Available = "available";
    public const string InstalledEnabled = "installed-enabled";
    public const string InstalledDisabled = "installed-disabled";
    public const string ReviewRequired = "review-required";
    public const string Blocked = "blocked";
}

public static class RulePackDependencyEdgeKinds
{
    public const string DependsOn = "depends-on";
    public const string ConflictsWith = "conflicts-with";
    public const string ForkedFrom = "forked-from";
}

public static class RulePackValidationIssueKinds
{
    public const string Manifest = "manifest";
    public const string Dependency = "dependency";
    public const string Compatibility = "compatibility";
    public const string Asset = "asset";
    public const string DeclarativeOverride = "declarative-override";
    public const string LuaProvider = "lua-provider";
    public const string Signature = "signature";
}

public sealed record RulePackWorkbenchListItem(
    ArtifactVersionReference RulePack,
    string Title,
    string InstallState,
    string Visibility,
    string TrustTier,
    IReadOnlyList<string> Targets,
    int DiagnosticCount = 0);

public sealed record RulePackDependencyNode(
    string NodeId,
    string Label,
    string Version,
    string Visibility,
    string TrustTier,
    bool IsSelected = false);

public sealed record RulePackDependencyEdge(
    string FromNodeId,
    string ToNodeId,
    string Kind,
    string Message);

public sealed record RulePackValidationIssue(
    string Kind,
    string Severity,
    string Message,
    string? AssetPath = null,
    string? SubjectId = null,
    string? ExplainEntryId = null);

public sealed record DeclarativeOverrideDraft(
    string OverrideId,
    string Mode,
    string TargetId,
    string Value,
    bool Enabled = true,
    string? Notes = null);

public sealed record RulePackLibraryProjection(
    IReadOnlyList<RulePackWorkbenchListItem> Items,
    string? SelectedPackId = null,
    string? ContinuationToken = null);

public sealed record RulePackInspectorProjection(
    RulePackManifest Manifest,
    string InstallState,
    IReadOnlyList<RulePackValidationIssue> Diagnostics,
    IReadOnlyList<RuntimeLockCompatibilityDiagnostic> CompatibilityDiagnostics,
    bool IsInstalled);

public sealed record RulePackDependencyGraphProjection(
    string PackId,
    IReadOnlyList<RulePackDependencyNode> Nodes,
    IReadOnlyList<RulePackDependencyEdge> Edges);

public sealed record RulePackValidationPanelProjection(
    string PackId,
    string Version,
    IReadOnlyList<RulePackValidationIssue> Issues,
    bool HasBlockingIssues);

public sealed record DeclarativeOverrideEditorProjection(
    string PackId,
    string Version,
    IReadOnlyList<DeclarativeOverrideDraft> Overrides,
    IReadOnlyList<string> SupportedModes,
    bool IsReadOnly = false);
