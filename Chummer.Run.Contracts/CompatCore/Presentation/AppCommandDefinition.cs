namespace Chummer.Contracts.Presentation;

public sealed record AppCommandDefinition(
    string Id,
    string LabelKey,
    string Group,
    bool RequiresOpenCharacter,
    bool EnabledByDefault,
    string RulesetId);
