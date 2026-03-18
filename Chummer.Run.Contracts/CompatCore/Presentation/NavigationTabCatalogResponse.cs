namespace Chummer.Contracts.Presentation;

public sealed record NavigationTabCatalogResponse(
    int Count,
    IReadOnlyList<NavigationTabDefinition> Tabs);
