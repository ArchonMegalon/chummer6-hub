using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Control.Contracts.Support;

namespace Chummer.Run.Api.Services.Support;

/// <summary>
/// Short-lived technical observations, separate from durable cases and account
/// state. One private Docker volume, one writer; no append-only Teable history,
/// backup export, email automation or public issue creation.
/// </summary>
public sealed class AndroidDiagnosticStore : IDisposable
{
    public const int MaximumReports = 512;
    public const int MaximumSnapshotBytes = 256 * 1024;
    public const int MaximumHourlyReports = 64;
    private readonly string? _path;
    private readonly string _readerToken;
    private readonly TimeProvider _clock;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly FileStream? _writerLease;
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
        { MaxDepth = 8, UnmappedMemberHandling = System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow };

    public AndroidDiagnosticStore(IConfiguration configuration, TimeProvider? clock = null)
    {
        _clock = clock ?? TimeProvider.System;
        _readerToken = configuration["CHUMMER_ANDROID_DIAGNOSTICS_READER_TOKEN"] ?? string.Empty;
        Enabled = configuration["CHUMMER_ANDROID_DIAGNOSTICS_ENABLED"] == "true";
        if (!Enabled) return;
        string? directory = configuration["CHUMMER_ANDROID_DIAGNOSTICS_DIRECTORY"];
        if (string.IsNullOrWhiteSpace(directory) || !Path.IsPathFullyQualified(directory)
            || _readerToken.Length is < 32 or > 256 || _readerToken.Any(c => c < '!' || c > '~'))
            throw new InvalidOperationException("Android diagnostics requires a private directory and scoped reader credential.");
        if (OperatingSystem.IsLinux()) Directory.CreateDirectory(directory, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        else Directory.CreateDirectory(directory);
        for (DirectoryInfo? info = new(directory); info is not null; info = info.Parent)
            if (info.LinkTarget is not null) throw new IOException("Diagnostic directory must not follow links.");
        if (OperatingSystem.IsLinux() && (File.GetUnixFileMode(directory) &
            (UnixFileMode.GroupRead | UnixFileMode.GroupWrite | UnixFileMode.GroupExecute |
             UnixFileMode.OtherRead | UnixFileMode.OtherWrite | UnixFileMode.OtherExecute)) != 0)
            throw new UnauthorizedAccessException("Diagnostic directory must be private.");
        _path = Path.Combine(directory, "observations.json");
        string lease = Path.Combine(directory, "writer.lock");
        if (new FileInfo(lease).LinkTarget is not null) throw new IOException("Diagnostic writer lease must not follow links.");
        _writerLease = new FileStream(lease, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
    }

    public bool Enabled { get; }

    public bool AuthorizeReader(string header)
    {
        const string prefix = "Bearer ";
        if (!Enabled || !header.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) || header.Length > 263) return false;
        byte[] supplied = SHA256.HashData(Encoding.UTF8.GetBytes(header[prefix.Length..]));
        byte[] expected = SHA256.HashData(Encoding.UTF8.GetBytes(_readerToken));
        return CryptographicOperations.FixedTimeEquals(supplied, expected);
    }

    public async Task<AndroidDiagnosticReceipt> SubmitAsync(AndroidDiagnosticReport report, CancellationToken ct)
    {
        EnsureEnabled();
        DateTimeOffset now = _clock.GetUtcNow();
        Validate(report, now);
        await _gate.WaitAsync(ct);
        try
        {
            var rows = Load();
            Prune(rows, now);
            var previous = rows.SingleOrDefault(row => row.Report.ReportId == report.ReportId);
            if (previous is not null)
            {
                if (previous.Report != report) throw new AndroidDiagnosticConflictException();
                return new(report.ReportId, previous.ReceivedAtUtc);
            }
            if (rows.Count >= MaximumReports || rows.Count(row => row.ReceivedAtUtc >= now.AddHours(-1)) >= MaximumHourlyReports)
                throw new AndroidDiagnosticCapacityException();
            rows.Add(new(report, now));
            await SaveAsync(rows, ct);
            return new(report.ReportId, now);
        }
        finally { _gate.Release(); }
    }

    public async Task<AndroidDiagnosticReadback> ReadAsync(CancellationToken ct)
    {
        EnsureEnabled();
        await _gate.WaitAsync(ct);
        try
        {
            var rows = Load();
            if (Prune(rows, _clock.GetUtcNow())) await SaveAsync(rows, ct);
            return new(rows.OrderByDescending(row => row.ReceivedAtUtc).ToArray());
        }
        finally { _gate.Release(); }
    }

    public async Task PruneAsync(CancellationToken ct)
    {
        if (!Enabled) return;
        await _gate.WaitAsync(ct);
        try
        {
            var rows = Load();
            if (Prune(rows, _clock.GetUtcNow())) await SaveAsync(rows, ct);
        }
        finally { _gate.Release(); }
    }

    private void EnsureEnabled()
    {
        if (!Enabled) throw new InvalidOperationException("Android diagnostics is not enabled.");
    }

    private static void Validate(AndroidDiagnosticReport? report, DateTimeOffset now)
    {
        if (report is null || report.ReportId == Guid.Empty || report.VersionCode is < 1 or > 2100000000
            || report.ObservedAtUtc < now.AddDays(-2) || report.ObservedAtUtc > now.AddMinutes(5)
            || report.ElapsedMilliseconds is < 0 or > 86400000
            || !Enum.IsDefined(report.Area) || !Enum.IsDefined(report.Operation)
            || !Enum.IsDefined(report.Outcome) || !Enum.IsDefined(report.Error))
            throw new ArgumentException("Invalid technical observation.");
    }

    private List<AndroidDiagnosticObservation> Load()
    {
        if (new FileInfo(_path!).LinkTarget is not null) throw new IOException("Diagnostic snapshot must not follow links.");
        if (!File.Exists(_path)) return new();
        using var stream = File.OpenRead(_path!);
        if (stream.Length > MaximumSnapshotBytes) throw new InvalidDataException("Diagnostic snapshot exceeds its bound.");
        var rows = JsonSerializer.Deserialize<List<AndroidDiagnosticObservation>>(stream, Json)
            ?? throw new InvalidDataException("Diagnostic snapshot is invalid.");
        if (rows.Count > MaximumReports || rows.Any(row => row?.Report is null || row.ReceivedAtUtc == default)
            || rows.Select(row => row.Report.ReportId).Distinct().Count() != rows.Count)
            throw new InvalidDataException("Diagnostic snapshot is invalid.");
        // Validate historical rows at receipt time; expiry is handled separately.
        foreach (var row in rows)
        {
            try { Validate(row.Report, row.ReceivedAtUtc); }
            catch (ArgumentException) { throw new InvalidDataException("Diagnostic snapshot contains invalid metadata."); }
        }
        return rows;
    }

    private async Task SaveAsync(List<AndroidDiagnosticObservation> rows, CancellationToken ct)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(rows, Json);
        if (bytes.Length > MaximumSnapshotBytes) throw new InvalidDataException("Diagnostic snapshot exceeds its bound.");
        string temporary = _path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            await using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                await stream.WriteAsync(bytes, ct);
                stream.Flush(flushToDisk: true);
            }
            ct.ThrowIfCancellationRequested();
            File.Move(temporary, _path!, overwrite: true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    private static bool Prune(List<AndroidDiagnosticObservation> rows, DateTimeOffset now)
        => rows.RemoveAll(row => row.ReceivedAtUtc < now.AddDays(-2)) > 0;

    public void Dispose() { _writerLease?.Dispose(); }
}

public sealed class AndroidDiagnosticConflictException : Exception;
public sealed class AndroidDiagnosticCapacityException : Exception;

public sealed class AndroidDiagnosticRetentionWorker(AndroidDiagnosticStore store,
    ILogger<AndroidDiagnosticRetentionWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!store.Enabled) return;
        using var timer = new PeriodicTimer(TimeSpan.FromMinutes(15));
        do
        {
            try { await store.PruneAsync(stoppingToken); }
            catch (Exception error) when (error is IOException or InvalidDataException or UnauthorizedAccessException or JsonException)
            { logger.LogWarning("Android diagnostic retention could not complete; intake remains fail-closed on invalid storage."); }
        } while (await timer.WaitForNextTickAsync(stoppingToken));
    }
}
