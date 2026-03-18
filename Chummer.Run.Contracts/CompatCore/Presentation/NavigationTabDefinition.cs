namespace Chummer.Contracts.Presentation;

public sealed record NavigationTabDefinition(
    string Id,
    string Label,
    string SectionId,
    string Group,
    bool RequiresOpenCharacter,
    bool EnabledByDefault,
    string RulesetId);
