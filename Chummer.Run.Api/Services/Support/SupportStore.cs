using System.Text.Json;
using Chummer.Run.Contracts.Support;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

namespace Chummer.Run.Api.Services.Support;

public sealed class SupportStore
{
    private readonly ILogger<SupportStore> _logger;
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public SupportStore(IConfiguration configuration, ILogger<SupportStore> logger)
    {
        _logger = logger;
        _storagePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();
    public string StoragePath => _storagePath;
    public Dictionary<string, CrashIncidentProjection> IncidentsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> IncidentIdByCrashId { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, CrashClusterProjection> ClustersById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> ClusterIdByFingerprint { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, CrashWorkItemProjection> WorkItemsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> WorkItemIdByClusterId { get; } = new(StringComparer.OrdinalIgnoreCase);

    public void PersistLocked()
    {
        SupportStoreSnapshot snapshot = new(
            IncidentsById: IncidentsById,
            IncidentIdByCrashId: IncidentIdByCrashId,
            ClustersById: ClustersById,
            ClusterIdByFingerprint: ClusterIdByFingerprint,
            WorkItemsById: WorkItemsById,
            WorkItemIdByClusterId: WorkItemIdByClusterId);

        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        string tempPath = $"{_storagePath}.tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions));
        File.Move(tempPath, _storagePath, true);
    }

    private void Load()
    {
        lock (Gate)
        {
            if (!File.Exists(_storagePath))
            {
                _logger.LogInformation("SupportStore starting with an empty durable state at {StoragePath}.", _storagePath);
                return;
            }

            string snapshotJson = File.ReadAllText(_storagePath);
            SupportStoreSnapshot snapshot = JsonSerializer.Deserialize<SupportStoreSnapshot>(snapshotJson, _jsonOptions)
                ?? throw new InvalidOperationException($"Unable to deserialize support store snapshot: {_storagePath}");
            ApplySnapshotLocked(snapshot);
            _logger.LogInformation(
                "SupportStore loaded {IncidentCount} crash incidents, {ClusterCount} clusters, and {WorkItemCount} work items from {StoragePath}.",
                IncidentsById.Count,
                ClustersById.Count,
                WorkItemsById.Count,
                _storagePath);
        }
    }

    private void ApplySnapshotLocked(SupportStoreSnapshot snapshot)
    {
        IncidentsById.Clear();
        IncidentIdByCrashId.Clear();
        ClustersById.Clear();
        ClusterIdByFingerprint.Clear();
        WorkItemsById.Clear();
        WorkItemIdByClusterId.Clear();

        CopyEntries(snapshot.IncidentsById, IncidentsById);
        CopyEntries(snapshot.IncidentIdByCrashId, IncidentIdByCrashId);
        CopyEntries(snapshot.ClustersById, ClustersById);
        CopyEntries(snapshot.ClusterIdByFingerprint, ClusterIdByFingerprint);
        CopyEntries(snapshot.WorkItemsById, WorkItemsById);
        CopyEntries(snapshot.WorkItemIdByClusterId, WorkItemIdByClusterId);
    }

    private static void CopyEntries<TValue>(
        IReadOnlyDictionary<string, TValue>? source,
        Dictionary<string, TValue> destination)
    {
        if (source is null)
        {
            return;
        }

        foreach ((string key, TValue value) in source)
        {
            destination[key] = value;
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_SUPPORT_STORE_PATH"] ?? configuration["Support:StorePath"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(Path.GetTempPath(), "chummer6-hub", "support-store.json");
    }
}

internal sealed record SupportStoreSnapshot(
    IReadOnlyDictionary<string, CrashIncidentProjection>? IncidentsById,
    IReadOnlyDictionary<string, string>? IncidentIdByCrashId,
    IReadOnlyDictionary<string, CrashClusterProjection>? ClustersById,
    IReadOnlyDictionary<string, string>? ClusterIdByFingerprint,
    IReadOnlyDictionary<string, CrashWorkItemProjection>? WorkItemsById,
    IReadOnlyDictionary<string, string>? WorkItemIdByClusterId);
