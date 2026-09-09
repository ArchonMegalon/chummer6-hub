using System.Text.Json;

namespace Chummer.Run.Api.Services.InstallLinking;

public sealed class InstallLinkedWorkspaceSnapshotStore
{
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true,
        // Core's bounded continuation envelope permits depth 128. Account for
        // this store's root/array/row wrappers without truncating opaque history.
        MaxDepth = 132
    };

    public InstallLinkedWorkspaceSnapshotStore(IConfiguration configuration)
    {
        _storagePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();

    public Dictionary<string, InstallLinkedWorkspaceSnapshotRecord> SnapshotsByKey { get; } = new(StringComparer.Ordinal);

    public void PersistLocked()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        string tempPath = $"{_storagePath}.tmp";
        Snapshot snapshot = new(
            SnapshotsByKey.Values
                .OrderBy(static item => item.OwnerKey, StringComparer.Ordinal)
                .ThenBy(static item => item.WorkspaceId, StringComparer.Ordinal)
                .ToArray());
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions));
        File.Move(tempPath, _storagePath, true);
    }

    public static string ComposeKey(string ownerKey, string workspaceId)
        // Keys are internal only; persisted rows retain their original typed
        // components. JSON framing avoids delimiter collisions on reload too.
        => JsonSerializer.Serialize(new[] { ownerKey, workspaceId.Trim() });

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
                if (!SnapshotsByKey.TryAdd(ComposeKey(record.OwnerKey, record.WorkspaceId), record))
                    throw new InvalidDataException("The workspace snapshot store contains duplicate identities.");
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
    bool Created,
    long RemoteRevision = 0,
    string? ServerToken = null,
    JsonElement? WorkspaceSnapshot = null,
    string? WorkspaceSnapshotDigest = null,
    JsonElement? WorkspaceContinuation = null,
    string? WorkspaceContinuationDigest = null);
