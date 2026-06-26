using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class HorizonArtifactUsageStore
{
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public HorizonArtifactUsageStore(IConfiguration configuration)
    {
        StoragePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();
    public string StoragePath { get; }
    internal List<HorizonArtifactUsageLedgerEntry> Entries { get; } = new();

    public void PersistLocked()
    {
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
