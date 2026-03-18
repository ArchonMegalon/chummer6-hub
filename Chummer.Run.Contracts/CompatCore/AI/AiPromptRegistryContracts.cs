namespace Chummer.Contracts.AI;

public static class AiPromptKinds
{
    public const string RouteSystem = "route-system";
}

public sealed record AiPromptCatalogQuery(
    string? RouteType = null,
    string? PersonaId = null,
    int MaxCount = 20);

public sealed record AiPromptDescriptor(
    string PromptId,
    string PromptKind,
    string RouteType,
    string RouteClassId,
    string PersonaId,
    string Title,
    string Summary,
    IReadOnlyList<string> BaseInstructions,
    IReadOnlyList<string> RequiredGroundingSectionIds,
    IReadOnlyList<string> RetrievalCorpusIds,
    IReadOnlyList<string> AllowedToolIds,
    bool EvidenceFirst = true,
    int MinFlavorPercent = 5,
    int MaxFlavorPercent = 15);

public sealed record AiPromptCatalog(
    IReadOnlyList<AiPromptDescriptor> Items,
    int TotalCount);
