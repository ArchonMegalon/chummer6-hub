using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api;

public sealed record HubApiGuardrailOptions
{
    public long MaxJsonBodyBytes { get; init; } = 1 * 1024 * 1024;

    public long MaxMultipartBodyBytes { get; init; } = 45 * 1024 * 1024;

    public long MaxReleaseBundleBodyBytes { get; init; } = 1024L * 1024 * 1024;

    public long MaxRequestBodyBytes { get; init; } = 50 * 1024 * 1024;

    public TimeSpan DefaultRequestTimeout { get; init; } = TimeSpan.FromSeconds(30);

    public TimeSpan ExtendedRequestTimeout { get; init; } = TimeSpan.FromMinutes(3);

    public TimeSpan ReleaseBundleTimeout { get; init; } = TimeSpan.FromMinutes(15);

    public int ApiReadRequestsPerMinute { get; init; } = 120;

    public int ApiWriteRequestsPerMinute { get; init; } = 40;

    public int PublicPageRequestsPerMinute { get; init; } = 240;

    public int FileTransferRequestsPerMinute { get; init; } = 60;

    public int RateLimitQueueLimit { get; init; } = 0;

    public int RateLimitSegmentsPerWindow { get; init; } = 4;

    public static HubApiGuardrailOptions FromConfiguration(IConfiguration configuration)
        => new()
        {
            MaxJsonBodyBytes = GetLong(configuration, "CHUMMER_API_MAX_JSON_BODY_BYTES", 1 * 1024 * 1024),
            MaxMultipartBodyBytes = GetLong(configuration, "CHUMMER_API_MAX_MULTIPART_BODY_BYTES", 45 * 1024 * 1024),
            MaxReleaseBundleBodyBytes = GetLong(configuration, "CHUMMER_API_MAX_RELEASE_BUNDLE_BODY_BYTES", 1024L * 1024 * 1024),
            MaxRequestBodyBytes = GetLong(configuration, "CHUMMER_API_MAX_REQUEST_BODY_BYTES", 50 * 1024 * 1024),
            DefaultRequestTimeout = TimeSpan.FromSeconds(GetInt(configuration, "CHUMMER_API_REQUEST_TIMEOUT_SECONDS", 30)),
            ExtendedRequestTimeout = TimeSpan.FromSeconds(GetInt(configuration, "CHUMMER_API_EXTENDED_TIMEOUT_SECONDS", 180)),
            ReleaseBundleTimeout = TimeSpan.FromSeconds(GetInt(configuration, "CHUMMER_API_RELEASE_BUNDLE_TIMEOUT_SECONDS", 900)),
            ApiReadRequestsPerMinute = GetInt(configuration, "CHUMMER_API_READ_RATE_LIMIT_PER_MINUTE", 120),
            ApiWriteRequestsPerMinute = GetInt(configuration, "CHUMMER_API_WRITE_RATE_LIMIT_PER_MINUTE", 40),
            PublicPageRequestsPerMinute = GetInt(configuration, "CHUMMER_API_PUBLIC_RATE_LIMIT_PER_MINUTE", 240),
            FileTransferRequestsPerMinute = GetInt(configuration, "CHUMMER_API_DOWNLOAD_RATE_LIMIT_PER_MINUTE", 60),
            RateLimitQueueLimit = GetInt(configuration, "CHUMMER_API_RATE_LIMIT_QUEUE", 0),
            RateLimitSegmentsPerWindow = GetInt(configuration, "CHUMMER_API_RATE_LIMIT_SEGMENTS", 4)
        };

    private static int GetInt(IConfiguration configuration, string key, int fallback)
    {
        string? raw = configuration[key];
        return int.TryParse(raw, out int parsed) && parsed > 0
            ? parsed
            : fallback;
    }

    private static long GetLong(IConfiguration configuration, string key, long fallback)
    {
        string? raw = configuration[key];
        return long.TryParse(raw, out long parsed) && parsed > 0
            ? parsed
            : fallback;
    }
}
