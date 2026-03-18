namespace Chummer.Contracts.Presentation;

public enum WorkspaceSurfaceActionKind
{
    Section = 0,
    Summary = 1,
    Validate = 2,
    Metadata = 3,
    Command = 4
}

public sealed record WorkspaceSurfaceActionDefinition(
    string Id,
    string Label,
    string TabId,
    WorkspaceSurfaceActionKind Kind,
    string TargetId,
    bool RequiresOpenCharacter,
    bool EnabledByDefault,
    string RulesetId);
