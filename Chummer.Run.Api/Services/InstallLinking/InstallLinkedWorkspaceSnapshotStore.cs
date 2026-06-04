using System.Text.Json;

namespace Chummer.Run.Api.Services.InstallLinking;

public sealed class InstallLinkedWorkspaceSnapshotStore
{
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public InstallLinkedWorkspaceSnapshotStore(IConfiguration configuration)
    {
        _storagePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();

    public Dictionary<string, InstallLinkedWorkspaceSnapshotRecord> SnapshotsByKey { get; } = new(StringComparer.OrdinalIgnoreCase);

    public void PersistLocked()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        string tempPath = $"{_storagePath}.tmp";
        Snapshot snapshot = new(
            SnapshotsByKey.Values
                .OrderBy(static item => item.OwnerKey, StringComparer.OrdinalIgnoreCase)
                .ThenBy(static item => item.WorkspaceId, StringComparer.OrdinalIgnoreCase)
                .ToArray());
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions));
        File.Move(tempPath, _storagePath, true);
    }

    public static string ComposeKey(string ownerKey, string workspaceId)
        => $"{ownerKey.Trim()}|{workspaceId.Trim()}";

    private void Load()
    {
        lock (Gate)
        {
            if (!File.Exists(_storagePath))
            {
                return;
            }

            Snapshot? snapshot = JsonSerializer.Deserialize<Snapshot>(File.ReadAllText(_storagePath), _jsonOptions);
            if (snapshot is null)
            {
                return;
            }

            SnapshotsByKey.Clear();
            foreach (InstallLinkedWorkspaceSnapshotRecord record in snapshot.Snapshots ?? Array.Empty<InstallLinkedWorkspaceSnapshotRecord>())
            {
                SnapshotsByKey[ComposeKey(record.OwnerKey, record.WorkspaceId)] = record;
            }
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        string configured =
            configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"]
            ?? configuration["InstallLinking:WorkspaceSnapshotStorePath"]
            ?? Path.Combine(Path.GetTempPath(), "chummer6-hub", "install-linked-workspace-snapshots.json");
        return Path.GetFullPath(configured);
    }

    private sealed record Snapshot(
        IReadOnlyList<InstallLinkedWorkspaceSnapshotRecord>? Snapshots = null);
}

public sealed record InstallLinkedWorkspaceSnapshotRecord(
    string OwnerKey,
    string WorkspaceId,
    string RulesetId,
    string Format,
    int SchemaVersion,
    string PayloadKind,
    string Payload,
    DateTimeOffset UpdatedAtUtc,
    string? OriginInstallationId,
    string? Name,
    string? Alias,
    string? Metatype,
    string? BuildMethod,
    string? CreatedVersion,
    string? AppVersion,
    decimal Karma,
    decimal Nuyen,
    bool Created);
