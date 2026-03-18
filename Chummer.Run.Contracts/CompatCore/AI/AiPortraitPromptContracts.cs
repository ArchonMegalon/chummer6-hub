namespace Chummer.Contracts.AI;

public static class AiPortraitPromptApiOperations
{
    public const string CreatePortraitPrompt = "create-portrait-prompt";
}

public static class AiPortraitPromptVariantKinds
{
    public const string Primary = "primary";
    public const string Mugshot = "mugshot";
    public const string Undercover = "undercover";
    public const string Dossier = "dossier";
}

public sealed record AiPortraitPromptRequest(
    string CharacterId,
    string? RuntimeFingerprint = null,
    string? StylePackId = null,
    string? PromptFlavor = null);

public sealed record AiPortraitPromptVariant(
    string Kind,
    string Title,
    string Prompt);

public sealed record AiPortraitPromptProjection(
    string CharacterId,
    string DisplayName,
    string RuntimeFingerprint,
    string RulesetId,
    string Prompt,
    IReadOnlyList<string> Tags,
    IReadOnlyList<string> Notes,
    IReadOnlyList<AiPortraitPromptVariant> Variants,
    string? StylePackId = null);
