using System.Text.Json;
using System.Text;
using Chummer.Run.Contracts.Billing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services.Community;

public sealed class BrilliantDirectoriesBillingStore
{
    private readonly ILogger<BrilliantDirectoriesBillingStore> _logger;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public BrilliantDirectoriesBillingStore(
        IConfiguration configuration,
        ILogger<BrilliantDirectoriesBillingStore>? logger = null)
    {
        _logger = logger ?? NullLogger<BrilliantDirectoriesBillingStore>.Instance;
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
                _logger.LogInformation("BrilliantDirectoriesBillingStore starting with an empty durable state at {StoragePath}.", StoragePath);
                return;
            }

            try
            {
                string storeJson = File.ReadAllText(StoragePath, Encoding.UTF8);
                if (string.IsNullOrWhiteSpace(storeJson))
                {
                    _logger.LogInformation("BrilliantDirectoriesBillingStore loaded an empty durable state from {StoragePath}.", StoragePath);
                    return;
                }

                var snapshot = JsonSerializer.Deserialize<BrilliantDirectoriesBillingStoreSnapshot>(
                    storeJson,
                    _jsonOptions);
                Members.Clear();
                Members.AddRange((snapshot?.Members ?? [])
                    .GroupBy(static item => item.UserId, StringComparer.OrdinalIgnoreCase)
                    .Select(static group => group.OrderByDescending(item => item.SyncedAtUtc).First()));
                _logger.LogInformation(
                    "BrilliantDirectoriesBillingStore loaded {MemberCount} member snapshots from {StoragePath}.",
                    Members.Count,
                    StoragePath);
            }
            catch (JsonException ex)
            {
                Members.Clear();
                QuarantineCorruptStoreFile();
                _logger.LogWarning(ex, "BrilliantDirectoriesBillingStore quarantined corrupt durable state at {StoragePath} and restarted empty.", StoragePath);
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
            // Starting empty is safer than crashing when a local billing store file is unreadable.
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
