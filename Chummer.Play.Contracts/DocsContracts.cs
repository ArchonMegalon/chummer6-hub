namespace Chummer.Play.Contracts.Docs;

public sealed record RuntimeDocQuery(
    string Query,
    string Context,
    int MaxResults = 5);

public sealed record RuntimeDocResult(
    string Query,
    IReadOnlyList<string> Matches,
    string? Evidence);
