using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text;
using System.Security.Cryptography;
using Chummer.Storage.Teable;

namespace Chummer.Run.Api.Services.InstallLinking;

public sealed class InstallLinkedWorkspaceSnapshotStore : IDisposable
{
    private readonly object _gate = new();
    private readonly TeableRevisionStore? _primary;
    private readonly bool _ownsPrimary;
    private readonly Dictionary<string, TeableRevisionStore.Head> _observedHeads = new(StringComparer.Ordinal);
    private string? _scopeOwner;
    private int _scopeDepth;
    private bool _failedScope;
    private const int MaximumPrimaryBytes = 64 * 1024 * 1024;
    private const string PrimarySchema = "chummer.hub.linked-workspace-primary/v1";
    private static readonly UTF8Encoding StrictUtf8 = new(false, true);
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true,
        // Core's bounded continuation envelope permits depth 128. Account for
        // this store's root/array/row wrappers without truncating opaque history.
        MaxDepth = 132
    };

    public InstallLinkedWorkspaceSnapshotStore(IConfiguration configuration, TeableRevisionStore? primary = null,
        bool ownsPrimary = false)
    {
        string mode = configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_STORAGE_PROVIDER"]?.Trim() ?? "local";
        if (mode is not ("local" or "teable") || (mode == "teable") != (primary is not null))
            throw new InvalidOperationException("Linked workspace storage requires an explicit matching primary configuration.");
        _primary = primary;
        _ownsPrimary = ownsPrimary;
        _storagePath = primary is null ? ResolveStoragePath(configuration) : string.Empty;
        if (primary is null) Load();
    }

    public object Gate => _primary is null || (Monitor.IsEntered(_gate) && _scopeDepth > 0 && !_failedScope)
        ? _gate : throw new InvalidOperationException("Primary workspace access requires a current owner scope.");

    public IDisposable Enter(string ownerKey)
    {
        Monitor.Enter(_gate);
        try
        {
            if (_primary is not null)
            {
                if (_scopeDepth == 0)
                {
                    _failedScope = false;
                    LoadPrimaryLocked(ownerKey);
                    _scopeOwner = ownerKey;
                }
                else if (_failedScope || !string.Equals(ownerKey, _scopeOwner, StringComparison.Ordinal))
                    throw new InvalidOperationException("A primary workspace scope cannot change owners or reuse a failed operation.");
            }
            _scopeDepth++;
            return new Scope(this);
        }
        catch (Exception exception)
        {
            if (_scopeDepth == 0 && _primary is not null) { SnapshotsByKey.Clear(); _scopeOwner = null; }
            Monitor.Exit(_gate);
            if (_primary is not null && IsPrimaryStorageFailure(exception))
                throw new InstallLinkingOperationException(StatusCodes.Status503ServiceUnavailable,
                    "The primary workspace state is unavailable; no local fallback was used.");
            throw;
        }
    }

    private sealed class Scope(InstallLinkedWorkspaceSnapshotStore store) : IDisposable
    {
        private bool _disposed;
        public void Dispose()
        {
            if (_disposed) return;
            if (!Monitor.IsEntered(store._gate))
                throw new InvalidOperationException("Workspace scopes are synchronous and thread-affine.");
            _disposed = true;
            store._scopeDepth--;
            if (store._scopeDepth == 0 && store._primary is not null)
            {
                store.SnapshotsByKey.Clear();
                store._scopeOwner = null;
            }
            Monitor.Exit(store._gate);
        }
    }

    public void Dispose() { if (_ownsPrimary) _primary?.Dispose(); }

    internal void EnsureAccountErasureSupported()
    {
        if (_primary is not null)
            throw new InvalidOperationException("Primary workspace historical erasure is not enabled; no deletion is claimed.");
    }

    public Dictionary<string, InstallLinkedWorkspaceSnapshotRecord> SnapshotsByKey { get; } = new(StringComparer.Ordinal);

    public void PersistLocked()
    {
        if (_primary is not null)
        {
            PersistPrimaryLocked();
            return;
        }
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

    internal static string OwnerStream(string ownerKey)
    {
        if (string.IsNullOrEmpty(ownerKey)
            || !(ownerKey.StartsWith("subject:", StringComparison.Ordinal) && ownerKey.Length > 8
                || ownerKey.StartsWith("user:", StringComparison.Ordinal) && ownerKey.Length > 5))
            throw new InvalidDataException("The primary workspace owner is invalid.");
        return "linked-workspaces-" + Convert.ToHexStringLower(SHA256.HashData(StrictUtf8.GetBytes(ownerKey)));
    }

    private void LoadPrimaryLocked(string ownerKey)
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        TeableRevisionStore.Head? head = null;
        try
        {
            head = _primary!.ReadAsync(OwnerStream(ownerKey), deadline.Token).GetAwaiter().GetResult();
            if (_observedHeads.TryGetValue(ownerKey, out var observed)
                && (head is null || head.Revision < observed.Revision
                    || (head.Revision == observed.Revision && (head.Commit != observed.Commit || head.Sha256 != observed.Sha256))))
                throw new InvalidDataException("The primary workspace authority regressed or changed identity.");
            InstallLinkedWorkspaceSnapshotRecord[] records = [];
            if (head is not null)
            {
                if (head.Bytes.Length > MaximumPrimaryBytes) throw new InvalidDataException("The primary workspace state is oversized.");
                var snapshot = JsonSerializer.Deserialize<PrimarySnapshot>(head.Bytes,
                    new JsonSerializerOptions(_jsonOptions) { UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow });
                if (snapshot is not { Schema: PrimarySchema, Snapshots: not null } || snapshot.OwnerKey != ownerKey)
                    throw new InvalidDataException("The primary workspace scope or schema is invalid.");
                records = ValidatePrimaryRecords(ownerKey, snapshot.Snapshots);
            }
            SnapshotsByKey.Clear();
            foreach (var record in records) SnapshotsByKey.Add(ComposeKey(record.OwnerKey, record.WorkspaceId), record);
            if (head is not null) _observedHeads[ownerKey] = head with { Bytes = [] };
        }
        catch { _failedScope = true; throw; }
        finally { if (head is not null) CryptographicOperations.ZeroMemory(head.Bytes); }
    }

    private void PersistPrimaryLocked()
    {
        if (!Monitor.IsEntered(_gate) || _scopeDepth == 0 || _scopeOwner is null || _failedScope)
            throw new InvalidOperationException("A current primary owner read is required before persisting workspaces.");
        byte[]? bytes = null;
        TeableRevisionStore.Head? written = null;
        try
        {
            var records = ValidatePrimaryRecords(_scopeOwner, SnapshotsByKey.Values.ToArray());
            if (SnapshotsByKey.Any(pair => pair.Key != ComposeKey(pair.Value.OwnerKey, pair.Value.WorkspaceId)))
                throw new InvalidDataException("The primary workspace key and identity disagree.");
            bytes = JsonSerializer.SerializeToUtf8Bytes(new PrimarySnapshot(PrimarySchema, _scopeOwner, records), _jsonOptions);
            if (bytes.Length > MaximumPrimaryBytes) throw new InvalidDataException("The primary workspace state is oversized.");
            _observedHeads.TryGetValue(_scopeOwner, out var expected);
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            written = _primary!.CompareExchangeAsync(OwnerStream(_scopeOwner), expected, Guid.NewGuid(), bytes,
                deadline.Token).GetAwaiter().GetResult();
            _observedHeads[_scopeOwner] = written with { Bytes = [] };
        }
        catch (Exception exception)
        {
            _failedScope = true;
            if (exception is TeableRevisionConflictException)
                throw new InstallLinkingOperationException(StatusCodes.Status409Conflict,
                    "The remote workspace changed. Read and review its current snapshot before updating it.");
            if (IsPrimaryStorageFailure(exception))
                throw new InstallLinkingOperationException(StatusCodes.Status503ServiceUnavailable,
                    "The primary workspace write was not confirmed; read current state before retrying.");
            throw;
        }
        finally
        {
            if (bytes is not null) CryptographicOperations.ZeroMemory(bytes);
            if (written is not null) CryptographicOperations.ZeroMemory(written.Bytes);
        }
    }

    private static InstallLinkedWorkspaceSnapshotRecord[] ValidatePrimaryRecords(string owner,
        IReadOnlyList<InstallLinkedWorkspaceSnapshotRecord> records)
    {
        var keys = new HashSet<string>(StringComparer.Ordinal);
        var validated = new List<InstallLinkedWorkspaceSnapshotRecord>(records.Count);
        foreach (var record in records)
        {
            if (record is null || record.OwnerKey != owner || string.IsNullOrWhiteSpace(record.WorkspaceId)
                || record.WorkspaceId != record.WorkspaceId.Trim() || record.WorkspaceId.Length > 128
                || !keys.Add(ComposeKey(owner, record.WorkspaceId)) || record.RemoteRevision <= 0
                || record.ServerToken is not { Length: 64 }
                || record.ServerToken.Any(c => c is not (>= '0' and <= '9' or >= 'a' and <= 'f'))
                || record.Payload is null || record.Payload.Length > InstallLinkedWorkspaceSnapshotService.MaxUpsertPayloadCharacters)
                throw new InvalidDataException("The primary workspace record identity or authority is invalid.");
            string? continuationOwner = null;
            if (record.WorkspaceContinuation is not null || record.WorkspaceContinuationDigest is not null)
            {
                if (!owner.StartsWith("subject:", StringComparison.Ordinal))
                    throw new InvalidDataException("A full continuation requires its exact subject owner.");
                continuationOwner = InstallLinkedWorkspaceSnapshotTransfer.ComputeContinuationOwnerId(owner[8..]);
            }
            validated.Add(InstallLinkedWorkspaceSnapshotTransfer.Validate(record, stored: true,
                expectedContinuationOwnerId: continuationOwner));
        }
        return validated.OrderBy(record => record.WorkspaceId, StringComparer.Ordinal).ToArray();
    }

    private static bool IsPrimaryStorageFailure(Exception exception)
        => exception is IOException or InvalidDataException or HttpRequestException or OperationCanceledException or JsonException or EncoderFallbackException;

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

    private sealed record PrimarySnapshot(string Schema, string OwnerKey, IReadOnlyList<InstallLinkedWorkspaceSnapshotRecord> Snapshots);
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
