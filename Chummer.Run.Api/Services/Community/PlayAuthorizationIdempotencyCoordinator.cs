using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.Api.Services.Community;

public sealed record PlayAuthorizationHttpEnvelope(int StatusCode, object? Body);

public sealed record PlayAuthorizationIdempotencyOutcome(
    bool FingerprintConflict,
    bool CapacityExceeded,
    PlayAuthorizationHttpEnvelope? Response);

/// <summary>
/// Process-local request coalescing for the explicitly single-writer Play authorization mode.
/// Cache keys and request fingerprints are digests so credentials and raw idempotency keys are
/// never retained. Failed operations are evicted so persistence rollback can be retried.
/// </summary>
public sealed class PlayAuthorizationIdempotencyCoordinator : IDisposable
{
    // Successful secret-bearing responses remain in memory only for this bounded retry window.
    // Production activation remains blocked until these receipts can be committed atomically
    // and recovered after a process crash without persisting plaintext capability material.
    private static readonly TimeSpan EntryLifetime = TimeSpan.FromMinutes(2);
    private const int MaximumEntries = 1024;
    private readonly ConcurrentDictionary<string, Entry> _entries = new(StringComparer.Ordinal);
    private readonly TimeProvider _timeProvider;
    private readonly ITimer _cleanupTimer;
    private int _entryCount;
    private long _utcHighWaterTicks;

    public PlayAuthorizationIdempotencyCoordinator(TimeProvider timeProvider)
    {
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
        _cleanupTimer = _timeProvider.CreateTimer(
            static state => ((PlayAuthorizationIdempotencyCoordinator)state!).RemoveExpired(),
            this,
            TimeSpan.FromMinutes(1),
            TimeSpan.FromMinutes(1));
    }

    public static bool ValidKey(string? key)
    {
        if (string.IsNullOrWhiteSpace(key) || key.Length is < 8 or > 128)
        {
            return false;
        }

        return key.All(character => char.IsAsciiLetterOrDigit(character)
            || character is '-' or '_' or ':' or '.');
    }

    public static string Fingerprint(params string?[] fields)
    {
        using IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        foreach (string? field in fields)
        {
            byte[] bytes = Encoding.UTF8.GetBytes(field ?? string.Empty);
            try
            {
                hash.AppendData(bytes);
                hash.AppendData(new byte[] { 0 });
            }
            finally
            {
                CryptographicOperations.ZeroMemory(bytes);
            }
        }

        return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
    }

    public async Task<PlayAuthorizationIdempotencyOutcome> ExecuteAsync(
        string scope,
        string idempotencyKey,
        string fingerprint,
        Func<Task<PlayAuthorizationHttpEnvelope>> action)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(scope);
        ArgumentException.ThrowIfNullOrWhiteSpace(idempotencyKey);
        ArgumentException.ThrowIfNullOrWhiteSpace(fingerprint);
        ArgumentNullException.ThrowIfNull(action);

        DateTimeOffset now = MonotonicUtcNow();
        RemoveExpired(now);
        string cacheKey = Fingerprint(scope, idempotencyKey);

        while (true)
        {
            if (_entries.TryGetValue(cacheKey, out Entry? existing))
            {
                if (existing.ExpiresAtUtc <= now && CanExpire(existing))
                {
                    RemoveIfSame(cacheKey, existing);
                    continue;
                }

                if (!FixedTimeDigestEquals(existing.Fingerprint, fingerprint))
                {
                    return new PlayAuthorizationIdempotencyOutcome(true, false, null);
                }

                return new PlayAuthorizationIdempotencyOutcome(
                    false,
                    false,
                    await existing.Response.Value.ConfigureAwait(false));
            }

            if (Interlocked.Increment(ref _entryCount) > MaximumEntries)
            {
                Interlocked.Decrement(ref _entryCount);
                return new PlayAuthorizationIdempotencyOutcome(false, true, null);
            }

            Entry candidate = new(
                fingerprint,
                now.Add(EntryLifetime),
                new Lazy<Task<PlayAuthorizationHttpEnvelope>>(action, LazyThreadSafetyMode.ExecutionAndPublication));
            if (!_entries.TryAdd(cacheKey, candidate))
            {
                Interlocked.Decrement(ref _entryCount);
                continue;
            }

            try
            {
                PlayAuthorizationHttpEnvelope response = await candidate.Response.Value.ConfigureAwait(false);
                if (response.StatusCode >= StatusCodes.Status500InternalServerError)
                {
                    RemoveIfSame(cacheKey, candidate);
                }

                return new PlayAuthorizationIdempotencyOutcome(false, false, response);
            }
            catch
            {
                RemoveIfSame(cacheKey, candidate);
                throw;
            }
        }
    }

    private void RemoveExpired(DateTimeOffset now)
    {
        foreach ((string key, Entry entry) in _entries)
        {
            if (entry.ExpiresAtUtc <= now && CanExpire(entry))
            {
                RemoveIfSame(key, entry);
            }
        }
    }

    private void RemoveExpired() => RemoveExpired(MonotonicUtcNow());

    private static bool CanExpire(Entry entry)
        => entry.Response.IsValueCreated && entry.Response.Value.IsCompleted;

    public void Dispose()
    {
        _cleanupTimer.Dispose();
        _entries.Clear();
        Volatile.Write(ref _entryCount, 0);
    }

    private void RemoveIfSame(string key, Entry expected)
    {
        if (_entries.TryGetValue(key, out Entry? current) && ReferenceEquals(current, expected))
        {
            if (((ICollection<KeyValuePair<string, Entry>>)_entries)
                .Remove(new KeyValuePair<string, Entry>(key, expected)))
            {
                Interlocked.Decrement(ref _entryCount);
            }
        }
    }

    private DateTimeOffset MonotonicUtcNow()
    {
        long observed = _timeProvider.GetUtcNow().UtcTicks;
        while (true)
        {
            long current = Volatile.Read(ref _utcHighWaterTicks);
            long next = Math.Max(current, observed);
            if (Interlocked.CompareExchange(ref _utcHighWaterTicks, next, current) == current)
            {
                return new DateTimeOffset(next, TimeSpan.Zero);
            }
        }
    }

    private static bool FixedTimeDigestEquals(string expected, string provided)
    {
        bool expectedValid = IsHexDigest(expected);
        bool providedValid = IsHexDigest(provided);
        byte[] expectedBytes = new byte[64];
        byte[] providedBytes = new byte[64];
        if (expectedValid)
        {
            Encoding.ASCII.GetBytes(expected, expectedBytes);
        }

        if (providedValid)
        {
            Encoding.ASCII.GetBytes(provided, providedBytes);
        }

        try
        {
            return expectedValid
                && providedValid
                && CryptographicOperations.FixedTimeEquals(expectedBytes, providedBytes);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(expectedBytes);
            CryptographicOperations.ZeroMemory(providedBytes);
        }
    }

    private static bool IsHexDigest(string value)
        => value.Length == 64
            && value.All(character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private sealed record Entry(
        string Fingerprint,
        DateTimeOffset ExpiresAtUtc,
        Lazy<Task<PlayAuthorizationHttpEnvelope>> Response);
}
