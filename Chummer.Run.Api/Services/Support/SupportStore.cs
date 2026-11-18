using System.Text.Json;
using System.Security.Cryptography;
using Chummer.Control.Contracts.Support;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

namespace Chummer.Run.Api.Services.Support;

public sealed class SupportStore : IDisposable
{
    private readonly object _gate = new();
    private readonly TeableRevisionStore? _primary;
    private readonly bool _ownsPrimary;
    private TeableRevisionStore.Head? _head;
    private bool _failed;
    private int _scopeDepth;
    private const string Stream = "support";
    private const string Schema = "chummer.hub.support-primary/v1";
    private const int MaximumBytes = 16 * 1024 * 1024;
    private sealed record Envelope(string Schema, SupportStoreSnapshot Snapshot);
    private readonly ILogger<SupportStore> _logger;
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public SupportStore(IConfiguration configuration, ILogger<SupportStore> logger,
        TeableRevisionStore? primary = null, bool ownsPrimary = false)
    {
        _logger = logger;
        string mode = configuration["CHUMMER_SUPPORT_STORAGE_PROVIDER"]?.Trim() ?? "local";
        if (mode is not ("local" or "teable") || (mode == "teable") != (primary is not null))
            throw new InvalidOperationException("Support storage requires an explicit matching primary configuration.");
        _primary = primary;
        _ownsPrimary = ownsPrimary;
        _storagePath = primary is null ? ResolveStoragePath(configuration) : string.Empty;
        if (primary is null) Load();
        else { using var scope = Enter(); }
    }

    public bool IsPrimary => _primary is not null;
    internal TeableRevisionStore? Primary => _primary;
    public object Gate => !IsPrimary || (Monitor.IsEntered(_gate) && _scopeDepth > 0)
        ? _gate : throw new InvalidOperationException("Primary support access requires a current store scope.");
    public string StoragePath => !IsPrimary ? _storagePath
        : throw new InvalidOperationException("Primary support storage has no authoritative local file.");
    public IDisposable Enter()
    {
        Monitor.Enter(_gate);
        try
        {
            EnsureUsable();
            if (IsPrimary && _scopeDepth == 0) LoadPrimaryLocked();
            _scopeDepth++;
            return new Scope(this);
        }
        catch { Monitor.Exit(_gate); throw; }
    }

    private sealed class Scope(SupportStore store) : IDisposable
    {
        private bool _disposed;
        public void Dispose()
        {
            if (_disposed) return;
            if (!Monitor.IsEntered(store._gate))
                throw new InvalidOperationException("Support scopes are synchronous and thread-affine.");
            _disposed = true;
            store._scopeDepth--;
            Monitor.Exit(store._gate);
        }
    }

    public void Dispose() { if (_ownsPrimary) _primary?.Dispose(); }
    private void EnsureUsable()
    {
        if (_failed) throw new InvalidOperationException("Support primary requires cold reconciliation.");
    }

    internal void EnsureAccountErasureSupported()
    {
        if (IsPrimary)
            throw new NotSupportedException("Primary support history and attachment erasure is not implemented.");
    }
    public Dictionary<string, SupportCaseProjection> CasesById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> CaseIdByClusterKey { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> CrashCaseIdByWorkItemId { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, CrashIncidentProjection> IncidentsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> IncidentIdByCrashId { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, CrashClusterProjection> ClustersById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> ClusterIdByFingerprint { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, CrashWorkItemProjection> WorkItemsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> WorkItemIdByClusterId { get; } = new(StringComparer.OrdinalIgnoreCase);
    internal Action? AccountErasurePersistenceFaultInjector { get; set; }

    public SupportReporterErasureResult EraseReporter(string? userId, string subjectId)
    {
        EnsureAccountErasureSupported();
        string normalizedSubject = NormalizeRequired(subjectId, nameof(subjectId));
        string? normalizedUser = NormalizeOptional(userId);
        lock (Gate)
        {
            // Establish a validated durable rollback point before deleting personal support content.
            PersistLocked();
            try
            {
                string[] caseIds = CasesById
                    .Where(pair => IdEquals(pair.Value.ReporterSubjectId, normalizedSubject)
                                   || (normalizedUser is not null && IdEquals(pair.Value.ReporterUserId, normalizedUser)))
                    .Select(static pair => pair.Key)
                    .ToArray();
                HashSet<string> removedCaseIds = caseIds.ToHashSet(StringComparer.OrdinalIgnoreCase);
                foreach (string caseId in caseIds)
                {
                    CasesById.Remove(caseId);
                }

                int indexRecordsRemoved = RemoveIndexValues(CaseIdByClusterKey, removedCaseIds)
                                          + RemoveIndexValues(CrashCaseIdByWorkItemId, removedCaseIds);
                AccountErasurePersistenceFaultInjector?.Invoke();
                PersistLocked();
                return new SupportReporterErasureResult(
                    Erased: caseIds.Length > 0,
                    CasesRemoved: caseIds.Length,
                    IndexRecordsRemoved: indexRecordsRemoved);
            }
            catch
            {
                Load();
                throw;
            }
        }
    }

    public void PersistLocked()
    {
        EnsureUsable();
        if (IsPrimary && (!Monitor.IsEntered(_gate) || _scopeDepth == 0))
            throw new InvalidOperationException("Primary support writes require a current store scope.");
        SupportStoreSnapshot snapshot = new(
            CasesById: CasesById,
            CaseIdByClusterKey: CaseIdByClusterKey,
            CrashCaseIdByWorkItemId: CrashCaseIdByWorkItemId,
            IncidentsById: IncidentsById,
            IncidentIdByCrashId: IncidentIdByCrashId,
            ClustersById: ClustersById,
            ClusterIdByFingerprint: ClusterIdByFingerprint,
            WorkItemsById: WorkItemsById,
            WorkItemIdByClusterId: WorkItemIdByClusterId);

        if (_primary is not null)
        {
            byte[]? bytes = null;
            TeableRevisionStore.Head? written = null;
            try
            {
                ValidatePrimary(snapshot);
                bytes = JsonSerializer.SerializeToUtf8Bytes(new Envelope(Schema, snapshot), _jsonOptions);
                if (bytes.Length > MaximumBytes) throw new InvalidDataException("Support primary snapshot is oversized.");
                // Crash intake's nested support-case upsert already includes all
                // incident/index state. Do not issue a second identical commit.
                if (_head?.Sha256 == Convert.ToHexStringLower(SHA256.HashData(bytes))) return;
                using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
                written = _primary.CompareExchangeAsync(Stream, _head, Guid.NewGuid(), bytes, deadline.Token)
                    .GetAwaiter().GetResult();
                _head = written with { Bytes = [] };
            }
            catch { _failed = true; throw; }
            finally
            {
                if (bytes is not null) CryptographicOperations.ZeroMemory(bytes);
                if (written is not null) CryptographicOperations.ZeroMemory(written.Bytes);
            }
            return;
        }
        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        string tempPath = $"{_storagePath}.tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions), System.Text.Encoding.UTF8);
        File.Move(tempPath, _storagePath, true);
    }

    private void LoadPrimaryLocked()
    {
        TeableRevisionStore.Head? head = null;
        try
        {
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            head = _primary!.ReadAsync(Stream, deadline.Token).GetAwaiter().GetResult();
            if (_head is not null && (head is null || head.Revision < _head.Revision
                || (head.Revision == _head.Revision && head.Sha256 != _head.Sha256)))
                throw new InvalidDataException("Support primary authority regressed or changed identity.");
            SupportStoreSnapshot snapshot;
            if (head is null) snapshot = new(null, null, null, null, null, null, null, null, null);
            else
            {
                if (head.Bytes.Length > MaximumBytes) throw new InvalidDataException("Support primary snapshot is oversized.");
                var envelope = JsonSerializer.Deserialize<Envelope>(head.Bytes, _jsonOptions);
                if (envelope is not { Schema: Schema, Snapshot: not null })
                    throw new InvalidDataException("Support primary schema is invalid.");
                snapshot = envelope.Snapshot;
                ValidatePrimary(snapshot);
            }
            ApplySnapshotLocked(snapshot);
            _head = head is null ? null : head with { Bytes = [] };
        }
        catch { _failed = true; throw; }
        finally { if (head is not null) CryptographicOperations.ZeroMemory(head.Bytes); }
    }

    private static void ValidatePrimary(SupportStoreSnapshot snapshot)
    {
        ValidateRows(snapshot.CasesById, item => item.CaseId);
        ValidateRows(snapshot.IncidentsById, item => item.IncidentId);
        ValidateRows(snapshot.ClustersById, item => item.ClusterId);
        ValidateRows(snapshot.WorkItemsById, item => item.WorkItemId);
        ValidateIndex(snapshot.CaseIdByClusterKey, snapshot.CasesById!, item => item.ClusterKey);
        ValidateIndex(snapshot.IncidentIdByCrashId, snapshot.IncidentsById!, item => item.Envelope?.CrashId ?? string.Empty);
        ValidateIndex(snapshot.ClusterIdByFingerprint, snapshot.ClustersById!, item => item.CrashFingerprint);
        ValidateIndex(snapshot.WorkItemIdByClusterId, snapshot.WorkItemsById!, item => item.ClusterId);
        ValidateIndex(snapshot.CrashCaseIdByWorkItemId, snapshot.CasesById!, item => item.ClusterKey["crash:".Length..],
            item => item.ClusterKey?.StartsWith("crash:", StringComparison.Ordinal) == true);
        foreach (var item in snapshot.CasesById!.Values)
        {
            if (string.IsNullOrWhiteSpace(item.ClusterKey) || string.IsNullOrWhiteSpace(item.Kind)
                || string.IsNullOrWhiteSpace(item.Status) || string.IsNullOrWhiteSpace(item.Title)
                || item.Detail is null || item.Summary is null
                || item.CreatedAtUtc == default || item.UpdatedAtUtc < item.CreatedAtUtc)
                throw new InvalidDataException("Support case content is invalid.");
            var attachments = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var attachment in item.Attachments ?? [])
            {
                if (attachment is null || !attachments.Add(attachment.AttachmentId)
                    || string.IsNullOrWhiteSpace(attachment.AttachmentId) || string.IsNullOrWhiteSpace(attachment.FileName)
                    || string.IsNullOrWhiteSpace(attachment.ContentType) || attachment.SizeBytes is < 1 or > SupportAttachmentStorageService.MaxAttachmentBytes)
                    throw new InvalidDataException("Support attachment metadata is invalid.");
            }
        }
        foreach (var item in snapshot.IncidentsById!.Values)
        {
            if (item.Envelope is null || item.RegistryContext is null
                || !snapshot.ClustersById!.TryGetValue(item.ClusterId, out var cluster)
                || !snapshot.WorkItemsById!.TryGetValue(item.WorkItemId, out var work)
                || work.ClusterId != item.ClusterId || item.Envelope.CrashFingerprint != cluster.CrashFingerprint
                || cluster.IncidentIds is null || !cluster.IncidentIds.Contains(item.IncidentId)
                || work.IncidentIds is null || !work.IncidentIds.Contains(item.IncidentId))
                throw new InvalidDataException("Support crash/index bindings are incomplete.");
        }
    }

    private static void ValidateRows<T>(IReadOnlyDictionary<string, T>? rows, Func<T, string> identity) where T : class
    {
        if (rows is null) throw new InvalidDataException("Support primary snapshot is incomplete.");
        var keys = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var (key, item) in rows)
            if (string.IsNullOrWhiteSpace(key) || key != key.Trim() || item is null
                || key != identity(item) || !keys.Add(key))
                throw new InvalidDataException("Support primary record identity is invalid.");
    }

    private static void ValidateIndex<T>(IReadOnlyDictionary<string, string>? index,
        IReadOnlyDictionary<string, T> rows, Func<T, string> identity, Func<T, bool>? included = null)
    {
        if (index is null) throw new InvalidDataException("Support primary index is missing.");
        var expected = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var (id, row) in rows)
        {
            if (included is not null && !included(row)) continue;
            string key = identity(row);
            if (string.IsNullOrWhiteSpace(key) || !expected.TryAdd(key, id))
                throw new InvalidDataException("Support primary index identity is ambiguous.");
        }
        if (index.Count != expected.Count || index.Any(pair => !expected.TryGetValue(pair.Key, out string? id) || id != pair.Value))
            throw new InvalidDataException("Support primary index does not match its records.");
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

            try
            {
                string snapshotJson = File.ReadAllText(_storagePath, System.Text.Encoding.UTF8);
                SupportStoreSnapshot snapshot = JsonSerializer.Deserialize<SupportStoreSnapshot>(snapshotJson, _jsonOptions)
                    ?? throw new InvalidOperationException($"Unable to deserialize support store snapshot: {_storagePath}");
                ApplySnapshotLocked(snapshot);
                _logger.LogInformation(
                    "SupportStore loaded {CaseCount} support cases, {IncidentCount} crash incidents, {ClusterCount} clusters, and {WorkItemCount} work items from {StoragePath}.",
                    CasesById.Count,
                    IncidentsById.Count,
                    ClustersById.Count,
                    WorkItemsById.Count,
                    _storagePath);
            }
            catch (JsonException ex)
            {
                ApplySnapshotLocked(new SupportStoreSnapshot(null, null, null, null, null, null, null, null, null));
                QuarantineCorruptStoreFile();
                _logger.LogWarning(ex, "SupportStore quarantined corrupt durable state at {StoragePath} and restarted empty.", _storagePath);
            }
        }
    }

    private void QuarantineCorruptStoreFile()
    {
        string quarantinePath = $"{_storagePath}.corrupt-{DateTimeOffset.UtcNow:yyyyMMddHHmmssfff}";
        try
        {
            File.Move(_storagePath, quarantinePath);
        }
        catch
        {
            // Starting empty is safer than crashing when a local support store file is unreadable.
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
        CasesById.Clear();
        CaseIdByClusterKey.Clear();
        CrashCaseIdByWorkItemId.Clear();

        CopyEntries(snapshot.CasesById, CasesById);
        CopyEntries(snapshot.CaseIdByClusterKey, CaseIdByClusterKey);
        CopyEntries(snapshot.CrashCaseIdByWorkItemId, CrashCaseIdByWorkItemId);
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

    private static int RemoveIndexValues(
        Dictionary<string, string> index,
        IReadOnlySet<string> removedValues)
    {
        string[] keys = index
            .Where(pair => removedValues.Contains(pair.Value))
            .Select(static pair => pair.Key)
            .ToArray();
        foreach (string key in keys)
        {
            index.Remove(key);
        }

        return keys.Length;
    }

    private static string NormalizeRequired(string value, string parameterName)
        => NormalizeOptional(value) ?? throw new ArgumentException($"{parameterName} is required.", parameterName);

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static bool IdEquals(string? left, string? right)
        => !string.IsNullOrWhiteSpace(left)
           && !string.IsNullOrWhiteSpace(right)
           && string.Equals(left.Trim(), right.Trim(), StringComparison.OrdinalIgnoreCase);
}

public sealed record SupportReporterErasureResult(
    bool Erased,
    int CasesRemoved,
    int IndexRecordsRemoved);

internal sealed record SupportStoreSnapshot(
    IReadOnlyDictionary<string, SupportCaseProjection>? CasesById,
    IReadOnlyDictionary<string, string>? CaseIdByClusterKey,
    IReadOnlyDictionary<string, string>? CrashCaseIdByWorkItemId,
    IReadOnlyDictionary<string, CrashIncidentProjection>? IncidentsById,
    IReadOnlyDictionary<string, string>? IncidentIdByCrashId,
    IReadOnlyDictionary<string, CrashClusterProjection>? ClustersById,
    IReadOnlyDictionary<string, string>? ClusterIdByFingerprint,
    IReadOnlyDictionary<string, CrashWorkItemProjection>? WorkItemsById,
    IReadOnlyDictionary<string, string>? WorkItemIdByClusterId);
