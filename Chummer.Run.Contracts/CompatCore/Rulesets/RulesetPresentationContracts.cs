using Chummer.Contracts.Presentation;

namespace Chummer.Contracts.Rulesets;

public interface IRulesetPlugin
{
    RulesetId Id { get; }

    string DisplayName { get; }

    IRulesetSerializer Serializer { get; }

    IRulesetShellDefinitionProvider ShellDefinitions { get; }

    IRulesetCatalogProvider Catalogs { get; }

    IRulesetCapabilityDescriptorProvider CapabilityDescriptors { get; }

    IRulesetCapabilityHost Capabilities { get; }

    IRulesetRuleHost Rules { get; }

    IRulesetScriptHost Scripts { get; }
}

public interface IRulesetShellDefinitionProvider
{
    IReadOnlyList<AppCommandDefinition> GetCommands();

    IReadOnlyList<NavigationTabDefinition> GetNavigationTabs();
}

public interface IRulesetCatalogProvider
{
    IReadOnlyList<WorkflowDefinition> GetWorkflowDefinitions() => System.Array.Empty<WorkflowDefinition>();

    IReadOnlyList<WorkflowSurfaceDefinition> GetWorkflowSurfaces() => System.Array.Empty<WorkflowSurfaceDefinition>();

    IReadOnlyList<WorkspaceSurfaceActionDefinition> GetWorkspaceActions();
}

public interface IRulesetPluginRegistry
{
    IReadOnlyList<IRulesetPlugin> All { get; }

    IRulesetPlugin? Resolve(string? rulesetId);
}

public interface IRulesetSelectionPolicy
{
    string GetDefaultRulesetId();
}

public sealed record RulesetSelectionOptions(
    string DefaultRulesetId = RulesetDefaults.Sr5,
    string Source = "built-in:sr5");

public interface IRulesetShellCatalogResolver
{
    IReadOnlyList<AppCommandDefinition> ResolveCommands(string? rulesetId);

    IReadOnlyList<NavigationTabDefinition> ResolveNavigationTabs(string? rulesetId);

    IReadOnlyList<WorkflowDefinition> ResolveWorkflowDefinitions(string? rulesetId);

    IReadOnlyList<WorkflowSurfaceDefinition> ResolveWorkflowSurfaces(string? rulesetId);

    IReadOnlyList<WorkspaceSurfaceActionDefinition> ResolveWorkspaceActionsForTab(string? tabId, string? rulesetId);
}
