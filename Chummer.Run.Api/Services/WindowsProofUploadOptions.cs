using System.Globalization;

namespace Chummer.Run.Api.Services;

public sealed record WindowsProofUploadOptions
{
    public const long MiB = 1024L * 1024L;

    public long MaxChunkBytes { get; init; } = 16L * MiB;
    public long MaxRequestBytes { get; init; } = 17L * MiB;
    public long MaxFileBytes { get; init; } = 256L * MiB;
    public long MaxSessionBytes { get; init; } = 384L * MiB;
    public int MaxFilesPerSession { get; init; } = 8;
    public int MaxChunksPerFile { get; init; } = 64;
    public int MaxPathBytes { get; init; } = 512;
    public TimeSpan SessionLifetime { get; init; } = TimeSpan.FromHours(6);
    public TimeSpan CompletedReceiptRetention { get; init; } = TimeSpan.FromDays(7);
    public bool Enabled { get; init; }
    public bool CfAccessGated { get; init; }

    public static WindowsProofUploadOptions FromConfiguration(IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        var options = new WindowsProofUploadOptions
        {
            MaxChunkBytes = ReadLong(configuration, "CHUMMER_WINDOWS_PROOF_UPLOAD_MAX_CHUNK_BYTES", 16L * MiB),
            MaxRequestBytes = ReadLong(configuration, "CHUMMER_WINDOWS_PROOF_UPLOAD_MAX_REQUEST_BYTES", 17L * MiB),
            MaxFileBytes = ReadLong(configuration, "CHUMMER_WINDOWS_PROOF_UPLOAD_MAX_FILE_BYTES", 256L * MiB),
            MaxSessionBytes = ReadLong(configuration, "CHUMMER_WINDOWS_PROOF_UPLOAD_MAX_SESSION_BYTES", 384L * MiB),
            MaxFilesPerSession = ReadInt(configuration, "CHUMMER_WINDOWS_PROOF_UPLOAD_MAX_FILES", 8),
            MaxChunksPerFile = ReadInt(configuration, "CHUMMER_WINDOWS_PROOF_UPLOAD_MAX_CHUNKS", 64),
            MaxPathBytes = ReadInt(configuration, "CHUMMER_WINDOWS_PROOF_UPLOAD_MAX_PATH_BYTES", 512),
            SessionLifetime = TimeSpan.FromMinutes(ReadInt(
                configuration,
                "CHUMMER_WINDOWS_PROOF_UPLOAD_SESSION_LIFETIME_MINUTES",
                360)),
            CompletedReceiptRetention = TimeSpan.FromHours(ReadInt(
                configuration,
                "CHUMMER_WINDOWS_PROOF_UPLOAD_COMPLETED_RETENTION_HOURS",
                168)),
            Enabled = ReadBoolean(configuration, "CHUMMER_WINDOWS_PROOF_UPLOAD_ENABLED", defaultValue: false),
            CfAccessGated = ReadBoolean(
                configuration,
                "CHUMMER_WINDOWS_PROOF_CF_ACCESS_GATED",
                defaultValue: false)
        };
        options.Validate();
        return options;
    }

    public void Validate()
    {
        if (MaxChunkBytes <= 0
            || MaxRequestBytes <= MaxChunkBytes
            || MaxFileBytes < MaxChunkBytes
            || MaxSessionBytes < MaxFileBytes
            || MaxFilesPerSession is < 1 or > 32
            || MaxChunksPerFile is < 1 or > 1024
            || MaxPathBytes is < 64 or > 4096
            || SessionLifetime <= TimeSpan.Zero
            || CompletedReceiptRetention <= TimeSpan.Zero)
        {
            throw new InvalidOperationException("Windows proof upload quota configuration is internally inconsistent.");
        }
    }

    private static long ReadLong(IConfiguration configuration, string key, long defaultValue)
    {
        string? raw = configuration[key];
        if (string.IsNullOrWhiteSpace(raw))
        {
            return defaultValue;
        }

        if (!long.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out long value) || value <= 0)
        {
            throw new InvalidOperationException($"{key} must be a positive integer byte count.");
        }

        return value;
    }

    private static int ReadInt(IConfiguration configuration, string key, int defaultValue)
    {
        string? raw = configuration[key];
        if (string.IsNullOrWhiteSpace(raw))
        {
            return defaultValue;
        }

        if (!int.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out int value) || value <= 0)
        {
            throw new InvalidOperationException($"{key} must be a positive integer.");
        }

        return value;
    }

    private static bool ReadBoolean(IConfiguration configuration, string key, bool defaultValue)
    {
        string? raw = configuration[key];
        if (string.IsNullOrWhiteSpace(raw))
        {
            return defaultValue;
        }

        if (!bool.TryParse(raw, out bool value))
        {
            throw new InvalidOperationException($"{key} must be 'true' or 'false'.");
        }

        return value;
    }
}
