using System.Collections.Concurrent;
using Microsoft.Extensions.Caching.Memory;

namespace Chummer.Run.Api.Services;

public sealed class HubGoogleAuthReplayCoordinator
{
    internal static HubGoogleAuthReplayCoordinator Shared { get; } = new();

    private readonly MemoryCache _completedFlows = new(new MemoryCacheOptions());
    private readonly ConcurrentDictionary<string, Task<GoogleAuthCompletionResult>> _inflightFlows = new(StringComparer.Ordinal);

    public async Task<GoogleAuthCompletionResult> CompleteOnceAsync(
        string flowKey,
        DateTimeOffset expiresAtUtc,
        Func<Task<GoogleAuthCompletionResult>> completeAsync,
        CancellationToken cancellationToken)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(flowKey);
        ArgumentNullException.ThrowIfNull(completeAsync);

        if (_completedFlows.TryGetValue(flowKey, out GoogleAuthCompletionResult? cached)
            && cached is not null)
        {
            return cached;
        }

        var completion = new TaskCompletionSource<GoogleAuthCompletionResult>(TaskCreationOptions.RunContinuationsAsynchronously);
        Task<GoogleAuthCompletionResult> sharedTask = _inflightFlows.GetOrAdd(flowKey, completion.Task);
        if (!ReferenceEquals(sharedTask, completion.Task))
        {
            return await sharedTask.WaitAsync(cancellationToken);
        }

        try
        {
            GoogleAuthCompletionResult result = await completeAsync();
            TimeSpan ttl = expiresAtUtc - DateTimeOffset.UtcNow;
            if (ttl < TimeSpan.FromSeconds(30))
            {
                ttl = TimeSpan.FromSeconds(30);
            }

            _completedFlows.Set(flowKey, result, ttl);
            completion.SetResult(result);
            return result;
        }
        catch (Exception ex)
        {
            completion.SetException(ex);
            throw;
        }
        finally
        {
            _inflightFlows.TryRemove(new KeyValuePair<string, Task<GoogleAuthCompletionResult>>(flowKey, completion.Task));
        }
    }
}
