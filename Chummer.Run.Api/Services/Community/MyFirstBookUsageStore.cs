using System.Text;
using System.Text.Json;
using Chummer.Storage.Teable;
using Chummer.Run.Contracts.Billing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services.Community;

public sealed class MyFirstBookUsageStore : IDisposable
{
    private readonly TeableQuotaLedger<MyFirstBookUsageLedgerEntry> _ledger;
    private readonly string _storagePath;
    private readonly ILogger<MyFirstBookUsageStore> _logger;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public MyFirstBookUsageStore(
        IConfiguration configuration,
        ILogger<MyFirstBookUsageStore>? logger = null,
        TeableRevisionStore? primary = null, bool ownsPrimary = false)
    {
        string mode = configuration["CHUMMER_MYFIRSTBOOK_USAGE_STORAGE_PROVIDER"]?.Trim() ?? "local";
        if (mode is not ("local" or "teable") || (mode == "teable") != (primary is not null))
            throw new InvalidOperationException("MyFirstBook usage requires an explicit matching primary configuration.");
        _ledger = new(primary, ownsPrimary, "myfirstbook-usage", "chummer.hub.myfirstbook-usage-primary/v1", ValidatePrimary);
        _logger = logger ?? NullLogger<MyFirstBookUsageStore>.Instance;
        _storagePath = primary is null ? ResolveStoragePath(configuration) : string.Empty;
        if (primary is null) Load();
    }

    public object Gate => _ledger.Gate;
    public string StoragePath => !_ledger.IsPrimary ? _storagePath
        : throw new InvalidOperationException("Primary MyFirstBook usage has no authoritative local file.");
    internal List<MyFirstBookUsageLedgerEntry> Entries => _ledger.Entries;
    public IDisposable Enter() => _ledger.Enter();
    public void Dispose() => _ledger.Dispose();
    internal void EnsureAccountErasureSupported() => _ledger.EnsureAccountErasureSupported();

    private static void ValidatePrimary(IReadOnlyList<MyFirstBookUsageLedgerEntry> entries)
    {
        var users = new Dictionary<string, HashSet<DateTimeOffset>>(StringComparer.OrdinalIgnoreCase);
        foreach (var entry in entries)
        {
            if (entry is null || string.IsNullOrWhiteSpace(entry.UserId) || entry.UserId != entry.UserId.Trim()
                || entry.MonthlyUsed < 0 || entry.WindowStartUtc == default || entry.WindowStartUtc.Offset != TimeSpan.Zero
                || entry.WindowStartUtc.Day != 1 || entry.WindowStartUtc.TimeOfDay != TimeSpan.Zero
                || entry.UpdatedAtUtc < entry.WindowStartUtc)
                throw new InvalidDataException("Primary MyFirstBook usage row is invalid.");
            if (!users.TryGetValue(entry.UserId, out var windows)) users.Add(entry.UserId, windows = []);
            if (!windows.Add(entry.WindowStartUtc)) throw new InvalidDataException("Primary MyFirstBook usage is ambiguous.");
        }
    }

    public void PersistLocked()
    {
        if (_ledger.IsPrimary) { _ledger.Persist(); return; }
        Directory.CreateDirectory(Path.GetDirectoryName(StoragePath)!);
        var snapshot = new MyFirstBookUsageStoreSnapshot(
            Entries
                .OrderByDescending(static item => item.WindowStartUtc)
                .ThenBy(static item => item.UserId, StringComparer.OrdinalIgnoreCase)
                .ToArray());
        string tempPath = $"{StoragePath}.tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions), Encoding.UTF8);
        File.Move(tempPath, StoragePath, true);
    }

    private void Load()
    {
        lock (Gate)
        {
            if (!File.Exists(StoragePath))
            {
                _logger.LogInformation("MyFirstBookUsageStore starting with an empty durable state at {StoragePath}.", StoragePath);
                return;
            }

            try
            {
                string storeJson = File.ReadAllText(StoragePath, Encoding.UTF8);
                if (string.IsNullOrWhiteSpace(storeJson))
                {
                    _logger.LogInformation("MyFirstBookUsageStore loaded an empty durable state from {StoragePath}.", StoragePath);
                    return;
                }

                var snapshot = JsonSerializer.Deserialize<MyFirstBookUsageStoreSnapshot>(storeJson, _jsonOptions);
                Entries.Clear();
                Entries.AddRange(snapshot?.Entries ?? []);
                _logger.LogInformation(
                    "MyFirstBookUsageStore loaded {EntryCount} quota ledger entries from {StoragePath}.",
                    Entries.Count,
                    StoragePath);
            }
            catch (JsonException ex)
            {
                Entries.Clear();
                QuarantineCorruptStoreFile();
                _logger.LogWarning(ex, "MyFirstBookUsageStore quarantined corrupt durable state at {StoragePath} and restarted empty.", StoragePath);
            }
        }
    }

    private void QuarantineCorruptStoreFile()
    {
        string quarantinePath = $"{StoragePath}.corrupt-{DateTimeOffset.UtcNow:yyyyMMddHHmmssfff}";
        try
        {
            File.Move(StoragePath, quarantinePath);
        }
        catch
        {
            // Starting empty is safer than crashing when a local usage ledger file is unreadable.
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"]
            ?? configuration["MyFirstBook:UsageStorePath"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(Path.GetTempPath(), "chummer6-hub", "myfirstbook-usage-store.json");
    }
}

internal sealed record MyFirstBookUsageStoreSnapshot(
    IReadOnlyList<MyFirstBookUsageLedgerEntry>? Entries);

internal sealed record MyFirstBookUsageLedgerEntry(
    string UserId,
    DateTimeOffset WindowStartUtc,
    int MonthlyUsed,
    DateTimeOffset UpdatedAtUtc);
