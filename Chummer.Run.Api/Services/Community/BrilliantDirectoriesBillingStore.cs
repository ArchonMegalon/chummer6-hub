using System.Text.Json;
using System.Text;
using Chummer.Run.Contracts.Billing;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class BrilliantDirectoriesBillingStore
{
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public BrilliantDirectoriesBillingStore(IConfiguration configuration)
    {
        StoragePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();
    public string StoragePath { get; }
    public List<BrilliantDirectoriesMemberSnapshotDto> Members { get; } = new();

    public void PersistLocked()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(StoragePath)!);
        var snapshot = new BrilliantDirectoriesBillingStoreSnapshot(
            Members
                .GroupBy(static item => item.UserId, StringComparer.OrdinalIgnoreCase)
                .Select(static group => group.OrderByDescending(item => item.SyncedAtUtc).First())
                .OrderByDescending(static item => item.SyncedAtUtc)
                .ToArray());
        var tempPath = $"{StoragePath}.tmp";
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

            var snapshot = JsonSerializer.Deserialize<BrilliantDirectoriesBillingStoreSnapshot>(
                storeJson,
                _jsonOptions);
            Members.Clear();
            Members.AddRange((snapshot?.Members ?? [])
                .GroupBy(static item => item.UserId, StringComparer.OrdinalIgnoreCase)
                .Select(static group => group.OrderByDescending(item => item.SyncedAtUtc).First()));
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        var configured = configuration["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"]
            ?? configuration["BrilliantDirectories:BillingStorePath"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(Path.GetTempPath(), "chummer6-hub", "brilliant-directories-billing-store.json");
    }
}

internal sealed record BrilliantDirectoriesBillingStoreSnapshot(
    IReadOnlyList<BrilliantDirectoriesMemberSnapshotDto>? Members);
