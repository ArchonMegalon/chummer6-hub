namespace Chummer.Contracts.Presentation;

public sealed record AppCommandCatalogResponse(
    int Count,
    IReadOnlyList<AppCommandDefinition> Commands);
