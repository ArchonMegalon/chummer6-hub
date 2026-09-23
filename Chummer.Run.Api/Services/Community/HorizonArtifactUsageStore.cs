using System.Text;
using System.Text.Json;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class HorizonArtifactUsageStore : IDisposable
{
    private readonly TeableQuotaLedger<HorizonArtifactUsageLedgerEntry> _ledger;
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public HorizonArtifactUsageStore(IConfiguration configuration, TeableRevisionStore? primary = null, bool ownsPrimary = false)
    {
        string mode = configuration["CHUMMER_HORIZON_ARTIFACT_USAGE_STORAGE_PROVIDER"]?.Trim() ?? "local";
        if (mode is not ("local" or "teable") || (mode == "teable") != (primary is not null))
            throw new InvalidOperationException("Artifact usage requires an explicit matching primary configuration.");
        _ledger = new(primary, ownsPrimary, "horizon-artifact-usage", "chummer.hub.horizon-artifact-usage-primary/v1", ValidatePrimary);
        _storagePath = primary is null ? ResolveStoragePath(configuration) : string.Empty;
        if (primary is null) Load();
    }

    public object Gate => _ledger.Gate;
    public string StoragePath => !_ledger.IsPrimary ? _storagePath
        : throw new InvalidOperationException("Primary artifact usage has no authoritative local file.");
    internal List<HorizonArtifactUsageLedgerEntry> Entries => _ledger.Entries;
    public IDisposable Enter() => _ledger.Enter();
    public void Dispose() => _ledger.Dispose();
    internal void EnsureAccountErasureSupported() => _ledger.EnsureAccountErasureSupported();

    private static void ValidatePrimary(IReadOnlyList<HorizonArtifactUsageLedgerEntry> entries)
    {
        var keys = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var row in entries)
        {
            if (row is null || new[] { row.UserId, row.HorizonId, row.CapabilityId, row.ArtifactKind }
                    .Any(value => string.IsNullOrWhiteSpace(value) || value != value.Trim())
                || row.Used < 0 || row.WindowKind != "weekly"
                || row.WindowStartUtc == default || row.WindowStartUtc.Offset != TimeSpan.Zero
                || row.WindowStartUtc.DayOfWeek != DayOfWeek.Monday || row.WindowStartUtc.TimeOfDay != TimeSpan.Zero
                || row.UpdatedAtUtc < row.WindowStartUtc)
                throw new InvalidDataException("Primary artifact usage row is invalid.");
            // JSON framing keeps identity components distinct; billing identity
            // equality remains the existing case-insensitive comparison.
            string key = JsonSerializer.Serialize(new[] { row.UserId.ToUpperInvariant(), row.HorizonId.ToUpperInvariant(), row.CapabilityId.ToUpperInvariant(),
                row.ArtifactKind.ToUpperInvariant(), row.WindowStartUtc.ToString("O", System.Globalization.CultureInfo.InvariantCulture) });
            if (!keys.Add(key)) throw new InvalidDataException("Primary artifact usage is ambiguous.");
        }
    }

    public void PersistLocked()
    {
        if (_ledger.IsPrimary) { _ledger.Persist(); return; }
        Directory.CreateDirectory(Path.GetDirectoryName(StoragePath)!);
        var snapshot = new HorizonArtifactUsageStoreSnapshot(
            Entries
                .OrderBy(static item => item.HorizonId, StringComparer.OrdinalIgnoreCase)
                .ThenBy(static item => item.ArtifactKind, StringComparer.OrdinalIgnoreCase)
                .ThenByDescending(static item => item.WindowStartUtc)
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

            var snapshot = JsonSerializer.Deserialize<HorizonArtifactUsageStoreSnapshot>(storeJson, _jsonOptions);
            Entries.Clear();
            Entries.AddRange(snapshot?.Entries ?? []);
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_HORIZON_ARTIFACT_USAGE_STORE_PATH"]
            ?? configuration["HorizonArtifacts:UsageStorePath"]
            ?? configuration["CHUMMER_RUNSITE_TOUR_USAGE_STORE_PATH"]
            ?? configuration["RunsiteTour:UsageStorePath"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(Path.GetTempPath(), "chummer6-hub", "horizon-artifact-usage-store.json");
    }
}

internal sealed record HorizonArtifactUsageStoreSnapshot(
    IReadOnlyList<HorizonArtifactUsageLedgerEntry>? Entries);

internal sealed record HorizonArtifactUsageLedgerEntry(
    string UserId,
    string HorizonId,
    string CapabilityId,
    string ArtifactKind,
    string WindowKind,
    DateTimeOffset WindowStartUtc,
    int Used,
    DateTimeOffset UpdatedAtUtc);
