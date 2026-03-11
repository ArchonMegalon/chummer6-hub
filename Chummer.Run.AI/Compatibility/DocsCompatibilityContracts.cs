namespace Chummer.Run.AI.Compatibility;

[Obsolete("Use Chummer.Run.Contracts.Docs.RuntimeDocQuery.")]
internal sealed record RuntimeDocQuery(
    string Query,
    string Context,
    int MaxResults = 5);

[Obsolete("Use Chummer.Run.Contracts.Docs.RuntimeDocResult.")]
internal sealed record RuntimeDocResult(
    string Query,
    IReadOnlyList<string> Matches,
    string? Evidence);
