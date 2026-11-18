using System.Collections.Concurrent;
using System.Diagnostics;

namespace Chummer.Storage.Teable;

/// <summary>
/// Spaces production requests across the process, including separate table/key
/// clients. Teable Cloud documents 10 requests/second. Four starts/second leaves
/// room for the separately hosted identity service and operator reads. This is
/// not a distributed quota or a retry policy; a remote 429 still fails closed.
/// </summary>
public sealed class TeableRequestPacingHandler(HttpMessageHandler inner) : DelegatingHandler(inner)
{
    private static readonly ConcurrentDictionary<string, OriginPace> Origins = new(StringComparer.Ordinal);
    private static readonly long SpacingTicks = (long)(Stopwatch.Frequency * 0.25);

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        var origin = request.RequestUri?.GetLeftPart(UriPartial.Authority)
            ?? throw new InvalidOperationException("Teable request requires an absolute origin.");
        var pace = Origins.GetOrAdd(origin, _ => new OriginPace());
        await pace.Gate.WaitAsync(ct).ConfigureAwait(false);
        Task<HttpResponseMessage> response;
        try
        {
            while (pace.NextStart - Stopwatch.GetTimestamp() is > 0 and var remaining)
                await Task.Delay(TimeSpan.FromSeconds((double)remaining / Stopwatch.Frequency), ct).ConfigureAwait(false);
            ct.ThrowIfCancellationRequested();
            // Start inside the admission gate. Release without waiting for the
            // response so slow reads do not serialize all network round trips.
            try { response = base.SendAsync(request, ct); }
            finally { pace.NextStart = Stopwatch.GetTimestamp() + SpacingTicks; }
        }
        finally { pace.Gate.Release(); }
        return await response.ConfigureAwait(false);
    }

    private sealed class OriginPace
    {
        public SemaphoreSlim Gate { get; } = new(1, 1);
        public long NextStart;
    }
}
