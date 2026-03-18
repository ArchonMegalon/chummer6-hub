namespace Chummer.Contracts.AI;

public static class AiEvaluationApiOperations
{
    public const string ListEvaluations = "list-evaluations";
}

public static class AiEvaluationStates
{
    public const string Pending = "pending";
    public const string Completed = "completed";
}

public sealed record AiEvaluationQuery(
    string? RouteType = null,
    int MaxCount = 20);

public sealed record AiEvaluationProjection(
    string EvaluationId,
    string RouteType,
    string Status,
    string Summary,
    DateTimeOffset CreatedAtUtc,
    string? ProviderId = null);

public sealed record AiEvaluationCatalog(
    IReadOnlyList<AiEvaluationProjection> Items,
    int TotalCount);
