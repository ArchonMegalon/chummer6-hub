using System.Text.Json;
using System.Text;
using Chummer.Run.Contracts.Billing;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services.Community;

public sealed class BrilliantDirectoriesBillingStore : IDisposable
{
    private readonly TeableQuotaLedger<BrilliantDirectoriesMemberSnapshotDto> _ledger;
    private readonly string _storagePath;
    private readonly ILogger<BrilliantDirectoriesBillingStore> _logger;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public BrilliantDirectoriesBillingStore(
        IConfiguration configuration,
        ILogger<BrilliantDirectoriesBillingStore>? logger = null,
        TeableRevisionStore? primary = null, bool ownsPrimary = false)
    {
        string mode = configuration["CHUMMER_BILLING_MEMBERSHIP_STORAGE_PROVIDER"]?.Trim() ?? "local";
        if (mode is not ("local" or "teable") || (mode == "teable") != (primary is not null))
            throw new InvalidOperationException("Membership storage requires an explicit matching primary configuration.");
        _ledger = new(primary, ownsPrimary, "billing-membership", "chummer.hub.billing-membership-primary/v1",
            rows => ValidatePrimary(rows, configuration));
        _logger = logger ?? NullLogger<BrilliantDirectoriesBillingStore>.Instance;
        _storagePath = primary is null ? ResolveStoragePath(configuration) : string.Empty;
        if (primary is null) Load();
    }

    public object Gate => _ledger.Gate;
    public string StoragePath => !_ledger.IsPrimary ? _storagePath
        : throw new InvalidOperationException("Primary membership storage has no authoritative local file.");
    public List<BrilliantDirectoriesMemberSnapshotDto> Members => _ledger.Entries;
    public IDisposable Enter() => _ledger.Enter();
    public void Dispose() => _ledger.Dispose();
    internal void EnsureAccountErasureSupported() => _ledger.EnsureAccountErasureSupported();

    private static void ValidatePrimary(IReadOnlyList<BrilliantDirectoriesMemberSnapshotDto> members, IConfiguration configuration)
    {
        var users = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var member in members)
        {
            BrilliantDirectoriesBillingService.ValidateStoredMembership(member, configuration);
            if (!users.Add(member.UserId)) throw new InvalidDataException("Primary membership has ambiguous user identities.");
        }
    }

    public void PersistLocked()
    {
        if (_ledger.IsPrimary) { _ledger.Persist(); return; }
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
