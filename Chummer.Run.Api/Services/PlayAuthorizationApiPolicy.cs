using System.Security.Cryptography;
using System.Text;
using System.Collections.Concurrent;

namespace Chummer.Run.Api.Services;

/// <summary>
/// Activation and service-authentication boundary for the dormant Play authorization API.
/// This policy deliberately supports only a declared single-writer deployment until the
/// CommunityStore has a cross-process compare-and-swap persistence implementation.
/// </summary>
public sealed class PlayAuthorizationApiPolicy
{
    public const string FeatureConfigurationKey = "CHUMMER_PLAY_AUTHORIZATION_API_ENABLED";
    public const string WriterModeConfigurationKey = "CHUMMER_PLAY_AUTHORIZATION_WRITER_MODE";
    public const string InternalApiKeyConfigurationKey = "CHUMMER_PLAY_HUB_INTERNAL_API_KEY";
    public const string InternalApiKeyHeader = "X-Chummer-Play-Service-Key";
    public const string SupportedWriterMode = "single_writer";
    public const string TestEnvironmentName = "Testing";
    public const string AccountPathPrefix = "/api/v1/accounts/me/play";
    public const string InternalPathPrefix = "/api/internal/play";

    private static readonly HashSet<string> PlaceholderSecrets = new(StringComparer.OrdinalIgnoreCase)
    {
        "change-me",
        "changeme",
        "default",
        "development",
        "password",
        "placeholder",
        "secret",
        "test"
    };

    private readonly IConfiguration _configuration;
    private readonly IHostEnvironment _environment;

    public PlayAuthorizationApiPolicy(IConfiguration configuration, IHostEnvironment environment)
    {
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        _environment = environment ?? throw new ArgumentNullException(nameof(environment));
    }

    public bool Enabled => _configuration.GetValue(FeatureConfigurationKey, false)
        && _environment.IsEnvironment(TestEnvironmentName);

    public static void ValidateStartup(IConfiguration configuration, IHostEnvironment environment)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        ArgumentNullException.ThrowIfNull(environment);

        if (!configuration.GetValue(FeatureConfigurationKey, false))
        {
            return;
        }

        string? writerMode = configuration[WriterModeConfigurationKey];
        if (!string.Equals(writerMode, SupportedWriterMode, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                $"{FeatureConfigurationKey} requires {WriterModeConfigurationKey}='{SupportedWriterMode}'. "
                + "Multi-instance Play authorization is intentionally unsupported until persistence provides cross-process compare-and-swap semantics.");
        }

        if (!IsStrongInternalApiKey(configuration[InternalApiKeyConfigurationKey]))
        {
            throw new InvalidOperationException(
                $"{FeatureConfigurationKey} requires a strong, non-placeholder {InternalApiKeyConfigurationKey}.");
        }

        if (!environment.IsEnvironment(TestEnvironmentName))
        {
            throw new InvalidOperationException(
                $"{FeatureConfigurationKey} remains test-only. Runtime activation is blocked until Play authorization has cross-replica compare-and-swap persistence, "
                + "crash-recoverable idempotency, trusted snapshot rollback detection, and proof-of-possession browser credentials.");
        }
    }

    public bool IsInternalRequestAuthorized(HttpRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        string? expected = _configuration[InternalApiKeyConfigurationKey];
        if (!IsStrongInternalApiKey(expected)
            || !request.Headers.TryGetValue(InternalApiKeyHeader, out var values)
            || values.Count != 1)
        {
            return false;
        }

        return FixedTimeSecretEquals(expected!, values[0]);
    }

    internal static bool IsStrongInternalApiKey(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)
            || value.Length < 43
            || value.Length > 512
            || PlaceholderSecrets.Contains(value)
            || value.Contains("change-me", StringComparison.OrdinalIgnoreCase)
            || value.Contains("placeholder", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        return value.Distinct().Take(12).Count() >= 12;
    }

    private static bool FixedTimeSecretEquals(string expected, string? provided)
    {
        byte[] expectedBytes = Encoding.UTF8.GetBytes(expected);
        byte[] providedBytes = Encoding.UTF8.GetBytes(provided ?? string.Empty);
        byte[] expectedHash = SHA256.HashData(expectedBytes);
        byte[] providedHash = SHA256.HashData(providedBytes);

        try
        {
            return CryptographicOperations.FixedTimeEquals(expectedHash, providedHash);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(expectedBytes);
            CryptographicOperations.ZeroMemory(providedBytes);
            CryptographicOperations.ZeroMemory(expectedHash);
            CryptographicOperations.ZeroMemory(providedHash);
        }
    }
}

public sealed class PlayAuthorizationRequestLimiter : IDisposable
{
    private static readonly TimeSpan Window = TimeSpan.FromMinutes(1);
    private static readonly TimeSpan BucketRetention = TimeSpan.FromMinutes(2);
    private const int AccountPermitLimit = 30;
    private const int InternalPermitLimit = 60;
    private const int MaximumBuckets = 4096;

    private readonly ConcurrentDictionary<string, Bucket> _buckets = new(StringComparer.Ordinal);
    private readonly TimeProvider _timeProvider;
    private readonly ITimer _cleanupTimer;
    private int _bucketCount;
    private int _cleanupCounter;
    private long _utcHighWaterTicks;

    public PlayAuthorizationRequestLimiter(TimeProvider timeProvider)
    {
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
        _cleanupTimer = _timeProvider.CreateTimer(
            static state => ((PlayAuthorizationRequestLimiter)state!).RemoveExpired(),
            this,
            TimeSpan.FromMinutes(1),
            TimeSpan.FromMinutes(1));
    }

    public bool TryAcquire(HttpContext context, bool internalRequest)
    {
        ArgumentNullException.ThrowIfNull(context);

        DateTimeOffset now = MonotonicUtcNow();
        if ((Interlocked.Increment(ref _cleanupCounter) & 63) == 0)
        {
            RemoveExpired(now);
        }

        string client = context.Connection.RemoteIpAddress?.ToString() ?? "unresolved";
        string key = internalRequest ? $"internal:{client}" : $"account:{client}";
        int limit = internalRequest ? InternalPermitLimit : AccountPermitLimit;
        while (true)
        {
            if (!TryGetOrCreateBucket(key, now, out Bucket? bucket))
            {
                return false;
            }

            lock (bucket!.Gate)
            {
                if (bucket.Removed)
                {
                    continue;
                }

                bucket.LastSeenAtUtc = now;
                if (now - bucket.WindowStartedAtUtc >= Window)
                {
                    bucket.WindowStartedAtUtc = now;
                    bucket.Count = 0;
                }

                if (bucket.Count >= limit)
                {
                    return false;
                }

                bucket.Count++;
                return true;
            }
        }
    }

    private bool TryGetOrCreateBucket(string key, DateTimeOffset now, out Bucket? bucket)
    {
        while (!_buckets.TryGetValue(key, out bucket))
        {
            if (Interlocked.Increment(ref _bucketCount) > MaximumBuckets)
            {
                Interlocked.Decrement(ref _bucketCount);
                RemoveExpired(now);
                if (Volatile.Read(ref _bucketCount) >= MaximumBuckets)
                {
                    bucket = null;
                    return false;
                }

                continue;
            }

            Bucket candidate = new(now);
            if (_buckets.TryAdd(key, candidate))
            {
                bucket = candidate;
                break;
            }

            Interlocked.Decrement(ref _bucketCount);
        }

        return true;
    }

    private void RemoveExpired(DateTimeOffset now)
    {
        foreach ((string key, Bucket bucket) in _buckets)
        {
            lock (bucket.Gate)
            {
                if (bucket.Removed || now - bucket.LastSeenAtUtc < BucketRetention)
                {
                    continue;
                }

                bucket.Removed = true;
            }

            if (((ICollection<KeyValuePair<string, Bucket>>)_buckets)
                .Remove(new KeyValuePair<string, Bucket>(key, bucket)))
            {
                Interlocked.Decrement(ref _bucketCount);
            }
        }
    }

    private void RemoveExpired() => RemoveExpired(MonotonicUtcNow());

    public void Dispose()
    {
        _cleanupTimer.Dispose();
        _buckets.Clear();
        Volatile.Write(ref _bucketCount, 0);
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

    private sealed class Bucket
    {
        public Bucket(DateTimeOffset windowStartedAtUtc)
        {
            WindowStartedAtUtc = windowStartedAtUtc;
            LastSeenAtUtc = windowStartedAtUtc;
        }

        public object Gate { get; } = new();
        public DateTimeOffset WindowStartedAtUtc { get; set; }
        public DateTimeOffset LastSeenAtUtc { get; set; }
        public int Count { get; set; }
        public bool Removed { get; set; }
    }
}

public static class PlayAuthorizationApiApplicationBuilderExtensions
{
    public static IApplicationBuilder UsePlayAuthorizationApiGate(this IApplicationBuilder app)
    {
        ArgumentNullException.ThrowIfNull(app);

        return app.Use(async (context, next) =>
        {
            PathString path = context.Request.Path;
            bool isAccountPath = path.StartsWithSegments(PlayAuthorizationApiPolicy.AccountPathPrefix);
            bool isInternalPath = path.StartsWithSegments(PlayAuthorizationApiPolicy.InternalPathPrefix);
            if (!isAccountPath && !isInternalPath)
            {
                await next().ConfigureAwait(false);
                return;
            }

            ApplyNoStoreHeaders(context.Response);
            PlayAuthorizationApiPolicy policy = context.RequestServices.GetRequiredService<PlayAuthorizationApiPolicy>();
            if (!policy.Enabled)
            {
                context.Response.StatusCode = StatusCodes.Status404NotFound;
                return;
            }

            PlayAuthorizationRequestLimiter limiter = context.RequestServices.GetRequiredService<PlayAuthorizationRequestLimiter>();
            if (!limiter.TryAcquire(context, isInternalPath))
            {
                context.Response.StatusCode = StatusCodes.Status429TooManyRequests;
                return;
            }

            if (isInternalPath && !policy.IsInternalRequestAuthorized(context.Request))
            {
                context.Response.StatusCode = StatusCodes.Status401Unauthorized;
                return;
            }

            await next().ConfigureAwait(false);
        });
    }

    public static void ApplyNoStoreHeaders(HttpResponse response)
    {
        ArgumentNullException.ThrowIfNull(response);
        response.Headers.CacheControl = "no-store, no-cache, max-age=0";
        response.Headers.Pragma = "no-cache";
        response.Headers.Expires = "0";
        response.Headers["Referrer-Policy"] = "no-referrer";
        response.Headers["X-Content-Type-Options"] = "nosniff";
    }
}
