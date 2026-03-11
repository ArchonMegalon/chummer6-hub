using System.Collections.Concurrent;

namespace Chummer.Run.AI.Services.Gateway;

public interface IConversationStore
{
    Task<ConversationAppendResult> AppendAsync(string sessionId, ConversationAppendRequest request, CancellationToken cancellationToken);
    IReadOnlyList<ConversationTurn> GetTurns(string sessionId);
}

public sealed class ConversationStore : IConversationStore
{
    private sealed record ConversationRecord(string SessionId, List<ConversationTurn> Turns);
    private readonly ConcurrentDictionary<string, ConversationRecord> _sessions = new();
    private readonly object _writeLock = new();

    public Task<ConversationAppendResult> AppendAsync(string sessionId, ConversationAppendRequest request, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (string.IsNullOrWhiteSpace(sessionId) || request is null)
        {
            throw new ArgumentException("sessionId and request are required.");
        }

        var record = _sessions.GetOrAdd(sessionId, key => new ConversationRecord(key, new List<ConversationTurn>()));

        lock (_writeLock)
        {
            record.Turns.Add(new ConversationTurn(
                Role: request.Role,
                Content: request.Content,
                AtUtc: DateTimeOffset.UtcNow));

            return Task.FromResult(new ConversationAppendResult(
                SessionId: record.SessionId,
                TotalTurns: record.Turns.Count));
        }
    }

    public IReadOnlyList<ConversationTurn> GetTurns(string sessionId)
    {
        if (string.IsNullOrWhiteSpace(sessionId))
        {
            return Array.Empty<ConversationTurn>();
        }

        return _sessions.TryGetValue(sessionId, out var record)
            ? record.Turns.ToArray()
            : Array.Empty<ConversationTurn>();
    }
}
