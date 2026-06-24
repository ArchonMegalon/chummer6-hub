using System.Text;
using System.Text.Json;
using Chummer.Run.Contracts.Billing;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class MyFirstBookUsageStore
{
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public MyFirstBookUsageStore(IConfiguration configuration)
    {
        StoragePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();
    public string StoragePath { get; }
    internal List<MyFirstBookUsageLedgerEntry> Entries { get; } = new();

    public void PersistLocked()
    {
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
                return;
            }

            string storeJson = File.ReadAllText(StoragePath, Encoding.UTF8);
            if (string.IsNullOrWhiteSpace(storeJson))
            {
                return;
            }

            var snapshot = JsonSerializer.Deserialize<MyFirstBookUsageStoreSnapshot>(storeJson, _jsonOptions);
            Entries.Clear();
            Entries.AddRange(snapshot?.Entries ?? []);
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
