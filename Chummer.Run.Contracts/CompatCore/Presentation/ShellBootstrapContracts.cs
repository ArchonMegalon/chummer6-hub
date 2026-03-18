using Chummer.Contracts.Content;
using Chummer.Contracts.Rulesets;
using Chummer.Contracts.Workspaces;

namespace Chummer.Contracts.Presentation;

public static class ShellBootstrapDefaults
{
    public const int MaxWorkspaces = 25;
}

public sealed record ShellPreferences(
    string PreferredRulesetId)
{
    public static ShellPreferences Default { get; } = new(string.Empty);
}

public sealed record ShellSessionState(
    string? ActiveWorkspaceId = null,
    string? ActiveTabId = null,
    IReadOnlyDictionary<string, string>? ActiveTabsByWorkspace = null)
{
    public static ShellSessionState Default { get; } = new();
}

public sealed record ShellBootstrapResponse(
    string RulesetId,
    IReadOnlyList<AppCommandDefinition> Commands,
    IReadOnlyList<NavigationTabDefinition> NavigationTabs,
    IReadOnlyList<WorkspaceListItemResponse> Workspaces,
    string PreferredRulesetId,
    string ActiveRulesetId,
    string? ActiveWorkspaceId = null,
    string? ActiveTabId = null,
    IReadOnlyDictionary<string, string>? ActiveTabsByWorkspace = null,
    IReadOnlyList<WorkflowDefinition>? WorkflowDefinitions = null,
    IReadOnlyList<WorkflowSurfaceDefinition>? WorkflowSurfaces = null,
    ActiveRuntimeStatusProjection? ActiveRuntime = null);

public sealed record ShellBootstrapSnapshot(
    string RulesetId,
    IReadOnlyList<AppCommandDefinition> Commands,
    IReadOnlyList<NavigationTabDefinition> NavigationTabs,
    IReadOnlyList<WorkspaceListItem> Workspaces,
    string PreferredRulesetId,
    string ActiveRulesetId,
    CharacterWorkspaceId? ActiveWorkspaceId = null,
    string? ActiveTabId = null,
    IReadOnlyDictionary<string, string>? ActiveTabsByWorkspace = null,
    IReadOnlyList<WorkflowDefinition>? WorkflowDefinitions = null,
    IReadOnlyList<WorkflowSurfaceDefinition>? WorkflowSurfaces = null,
    ActiveRuntimeStatusProjection? ActiveRuntime = null);
