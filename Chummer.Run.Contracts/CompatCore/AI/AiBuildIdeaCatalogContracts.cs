namespace Chummer.Contracts.AI;

public sealed record AiBuildIdeaCatalogQuery(
    string RouteType = AiRouteTypes.Build,
    string QueryText = "",
    string? RulesetId = null,
    int MaxCount = 10);

public sealed record AiBuildIdeaCatalog(
    IReadOnlyList<BuildIdeaCard> Items,
    int TotalCount);
