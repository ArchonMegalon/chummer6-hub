using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Api.Services.Teable;

namespace Chummer.Run.Api.Services.Community;

/// <summary>
/// Durable private authoring requests. Does not execute a provider or reserve
/// credits. A worker must separately obtain execution/quota authority. The
/// durable dispatch fence is never automatically reset after a lost response.
/// </summary>
public sealed class OriginChapterAuthoringService : IDisposable
{
    private readonly IConfiguration configuration;
    private readonly TeableOriginChapterStorage? _primary;
    private TeableOriginChapterStorage.Session? _primarySession;
    public OriginChapterAuthoringService(IConfiguration configuration, TeableOriginChapterStorage? primary = null)
    {
        this.configuration = configuration;
        string provider = configuration["CHUMMER_ORIGIN_CHAPTER_STORAGE_PROVIDER"]?.Trim() ?? "local";
        if (provider is not ("local" or "teable") || (provider == "teable") != (primary is not null))
            throw new InvalidOperationException("Origin storage provider and registration do not match.");
        _primary = primary;
    }

    public void Dispose() => _primary?.Dispose();
    public const int MaximumRequestBytes = 64 * 1024;
    public const int MaximumDraftBytes = 64 * 1024;
    private const int MaximumFileBytes = 512 * 1024;
    private const string Schema = "chummer.origin.chapter-job/v1";
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { MaxDepth = 16 };
    private readonly object _gate = new();
    private sealed record StoredJob(string Schema, string OwnerDigest, OriginChapterAuthoringJob Job, string Digest,
        string? ExecutionAdmission = null);

    public bool IsConfigured => _primary is not null || !string.IsNullOrWhiteSpace(configuration["CHUMMER_RUNTIME_STATE_ROOT"]);

    public OriginChapterAuthoringJob Create(string subjectId, OriginChapterAuthoringRequest request, Func<bool> stillAuthorized)
    {
        ArgumentNullException.ThrowIfNull(request);
        RequireId(request.RequestId);
        if (!request.ExternalProcessingConsent) throw new ArgumentException("External processing consent is required.");
        OriginChapterSource source = OriginChapterSourceIdentity.Capture(request.Source);
        string sourceDigest = OriginChapterSourceIdentity.Digest(source);
        return Locked(root =>
        {
            if (!stillAuthorized()) throw new UnauthorizedAccessException();
            string owner = Owner(subjectId);
            string path = JobPath(root, owner, request.RequestId);
            if (Read(path, owner, request.RequestId) is { } existing)
            {
                if (existing.SourceDigest != sourceDigest)
                    throw new InvalidOperationException("The authoring request already belongs to a different source.");
                return existing;
            }
            if (_primarySession is not null)
                _primarySession.Register(WorkId(owner, request.RequestId));
            else if (Directory.EnumerateFiles(root, owner + ".*.json").Take(128).Count() >= 128
                || Directory.EnumerateFiles(root, "*.json").Take(2048).Count() >= 2048)
                throw new InvalidOperationException("The private authoring queue is full.");
            if (!stillAuthorized()) throw new UnauthorizedAccessException();
            var job = new OriginChapterAuthoringJob(request.RequestId, sourceDigest, source,
                OriginChapterAuthoringStates.AwaitingAuthoring, "first_book_ai", null, null);
            Write(path, owner, job);
            return job;
        });
    }

    public OriginChapterAuthoringJob? Get(string subjectId, string requestId)
    {
        RequireId(requestId);
        return Locked(root => Read(JobPath(root, Owner(subjectId), requestId), Owner(subjectId), requestId));
    }

    public OriginChapterAuthoringJob AcceptReading(string subjectId, string requestId, string sourceDigest,
        string providerReceiptDigest, string textDigest, bool explicitlyConfirmed, Func<bool> stillAuthorized)
    {
        RequireId(requestId);
        if (!explicitlyConfirmed || !IsDigest(sourceDigest) || !IsDigest(providerReceiptDigest) || !IsDigest(textDigest))
            throw new ArgumentException("Exact reader confirmation is required.");
        return Locked(root =>
        {
            if (!stillAuthorized()) throw new UnauthorizedAccessException();
            string owner = Owner(subjectId);
            string path = JobPath(root, owner, requestId);
            var stored = ReadStored(path, owner, requestId) ?? throw new KeyNotFoundException();
            var job = stored.Job;
            if (job.State != OriginChapterAuthoringStates.ReviewRequired || job.SourceDigest != sourceDigest
                || job.ProviderReceiptDigest != providerReceiptDigest || TextDigest(job.DraftText!) != textDigest)
                throw new InvalidOperationException("The reviewed text or source changed.");
            if (job.ReaderAcceptedTextDigest is not null) return job;
            var accepted = job with { ReaderAcceptedTextDigest = textDigest };
            Write(path, owner, accepted, stored.ExecutionAdmission);
            return accepted;
        });
    }

    // Provider workers get opaque work identities, not identity subjects or
    // install credentials. This seam does not select accounts or authorize quota.
    internal IReadOnlyList<OriginChapterWorkerItem> PendingForWorker(int limit)
    {
        if (limit is < 1 or > 20) throw new ArgumentException("Invalid worker page size.");
        return Locked(root => WorkIds(root).Order(StringComparer.Ordinal)
            .Select(workId => ReadStored(Path.Combine(root, workId + ".json"), workId[..64], null))
            // A remote catalogue reservation may outlive an interrupted initial
            // create. Missing bytes are inert, never permission to generate.
            .Where(stored => stored is not null && stored.Job.State != OriginChapterAuthoringStates.ReviewRequired)
            .Select(stored => stored!)
            .Take(limit).Select(WorkerItem).ToArray());
    }

    private IEnumerable<string> WorkIds(string root)
    {
        if (_primarySession is not null) return _primarySession.WorkIds();
        return Directory.EnumerateFiles(root, "*.json").Select(path =>
        {
            string workId = Path.GetFileNameWithoutExtension(path);
            TeableOriginChapterStorage.ValidateWorkId(workId);
            return workId;
        });
    }

    internal OriginChapterWorkerItem GetForWorker(string workId)
        => Locked(root => WorkerItem(ReadWorkerRecord(root, workId)));

    internal OriginChapterWorkerAdmission AdmitForWorker(string workId, string sourceDigest, string executionAdmission)
    {
        RequireId(executionAdmission);
        return Locked(root =>
        {
            StoredJob stored = ReadWorkerRecord(root, workId);
            if (stored.Job.SourceDigest != sourceDigest)
                throw new InvalidOperationException("The authoring source changed.");
            if (stored.ExecutionAdmission is not null)
            {
                if (stored.ExecutionAdmission != executionAdmission)
                    throw new InvalidOperationException("The request has a different execution admission.");
                return new OriginChapterWorkerAdmission(WorkerItem(stored), MayStartGeneration: false);
            }
            if (stored.Job.State != OriginChapterAuthoringStates.AwaitingAuthoring)
                throw new InvalidOperationException("Reconcile this existing dispatch; do not redispatch.");
            var fenced = stored.Job with { State = OriginChapterAuthoringStates.ReconciliationRequired };
            string path = JobPath(root, stored.OwnerDigest, fenced.RequestId);
            Write(path, stored.OwnerDigest, fenced, executionAdmission);
            return new OriginChapterWorkerAdmission(WorkerItem(ReadWorkerRecord(root, workId)), MayStartGeneration: true);
        });
    }

    internal OriginChapterWorkerItem CompleteForWorker(string workId, string sourceDigest, string executionAdmission,
        string draftText, string providerReceiptDigest)
    {
        RequireId(executionAdmission);
        ValidateResult(draftText, providerReceiptDigest);
        return Locked(root =>
        {
            StoredJob stored = ReadWorkerRecord(root, workId);
            if (stored.ExecutionAdmission != executionAdmission || stored.Job.SourceDigest != sourceDigest)
                throw new InvalidOperationException("The admitted chapter source does not match.");
            OriginChapterAuthoringJob completed = Completed(stored.Job, draftText, providerReceiptDigest);
            Write(JobPath(root, stored.OwnerDigest, completed.RequestId), stored.OwnerDigest, completed, executionAdmission);
            return WorkerItem(ReadWorkerRecord(root, workId));
        });
    }

    // Trusted worker seam, deliberately not a public HTTP endpoint. A successful
    // fence is not credit approval. Recovery reads/reconciles the provider job;
    // it must not call generation again when this method returns false.
    internal bool TryFenceDispatch(string subjectId, string requestId, string sourceDigest)
        => Locked(root =>
        {
            string owner = Owner(subjectId);
            string path = JobPath(root, owner, requestId);
            var job = Read(path, owner, requestId) ?? throw new KeyNotFoundException();
            if (job.SourceDigest != sourceDigest) throw new InvalidOperationException("The authoring source changed.");
            if (job.State != OriginChapterAuthoringStates.AwaitingAuthoring) return false;
            Write(path, owner, job with { State = OriginChapterAuthoringStates.ReconciliationRequired });
            return true;
        });

    internal OriginChapterAuthoringJob Complete(string subjectId, string requestId, string sourceDigest,
        string draftText, string providerReceiptDigest)
    {
        ValidateResult(draftText, providerReceiptDigest);
        return Locked(root =>
        {
            string owner = Owner(subjectId);
            string path = JobPath(root, owner, requestId);
            var stored = ReadStored(path, owner, requestId) ?? throw new KeyNotFoundException();
            var job = stored.Job;
            if (job.SourceDigest != sourceDigest) throw new InvalidOperationException("The authoring source changed.");
            if (stored.ExecutionAdmission is not null)
                throw new InvalidOperationException("Use the bound worker completion path for this admitted job.");
            var result = Completed(job, draftText, providerReceiptDigest);
            Write(path, owner, result);
            return result;
        });
    }

    private static void ValidateResult(string draftText, string providerReceiptDigest)
    {
        if (string.IsNullOrWhiteSpace(draftText) || Encoding.UTF8.GetByteCount(draftText) > MaximumDraftBytes
            || !IsDigest(providerReceiptDigest)) throw new ArgumentException("The chapter result is invalid or oversized.");
    }

    private static OriginChapterAuthoringJob Completed(OriginChapterAuthoringJob job, string text, string receipt)
    {
        if (job.State == OriginChapterAuthoringStates.ReviewRequired)
        {
            if (job.DraftText != text || job.ProviderReceiptDigest != receipt)
                throw new InvalidOperationException("A retained chapter result cannot be replaced.");
            return job;
        }
        if (job.State != OriginChapterAuthoringStates.ReconciliationRequired)
            throw new InvalidOperationException("This authoring request was not dispatched.");
        return job with { State = OriginChapterAuthoringStates.ReviewRequired, DraftText = text, ProviderReceiptDigest = receipt };
    }

    public int EraseForSubject(string subjectId)
    {
        if (_primary is not null)
            throw new InvalidOperationException("Primary authoring erasure requires historical payload cleanup before activation.");
        if (!IsConfigured) return 0;
        return Locked(root =>
        {
            string owner = Owner(subjectId);
            // A crash between flush and rename may leave an owned temporary
            // source packet. Account erasure also removes these exact files.
            string[] paths = Directory.EnumerateFiles(root, owner + ".*")
                .Where(path =>
                {
                    string[] parts = Path.GetFileName(path).Split('.');
                    return parts.Length is 3 or 4 && parts[0] == owner && IsDigest(parts[1]) && parts[2] == "json"
                        && (parts.Length == 3 || parts[3].StartsWith("tmp-", StringComparison.Ordinal)
                            && Guid.TryParseExact(parts[3][4..], "N", out _));
                }).ToArray();
            foreach (string path in paths) { RejectLink(path); File.Delete(path); }
            return paths.Length;
        });
    }

    private T Locked<T>(Func<string, T> operation)
    {
        if (!IsConfigured) throw new InvalidOperationException("Private authoring storage is not configured.");
        lock (_gate)
        {
            if (_primary is not null)
            {
                if (_primarySession is not null) throw new InvalidOperationException("Primary authoring operations cannot be nested.");
                using var session = _primary.OpenSession();
                _primarySession = session;
                try { return operation(string.Empty); }
                finally { _primarySession = null; }
            }
            string root = Path.GetFullPath(Path.Combine(configuration["CHUMMER_RUNTIME_STATE_ROOT"]!, "origin-chapter-jobs"));
            for (string? part = root; part is not null; part = Path.GetDirectoryName(part))
                if (Directory.Exists(part) || File.Exists(part)) RejectLink(part);
            if (OperatingSystem.IsWindows()) Directory.CreateDirectory(root);
            else Directory.CreateDirectory(root, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
            string lockPath = Path.Combine(root, ".writer.lock");
            RejectLink(lockPath);
            using var custody = OpenPrivate(lockPath, FileMode.OpenOrCreate);
            return operation(root);
        }
    }

    private OriginChapterAuthoringJob? Read(string path, string owner, string requestId)
        => ReadStored(path, owner, requestId)?.Job;

    private StoredJob? ReadStored(string path, string owner, string? requestId)
    {
        if (_primarySession is not null)
        {
            byte[]? primaryBytes = _primarySession.Read(Path.GetFileNameWithoutExtension(path));
            if (primaryBytes is null) return null;
            try { return DecodeStored(primaryBytes, path, owner, requestId); }
            finally { CryptographicOperations.ZeroMemory(primaryBytes); }
        }
        RejectLink(path);
        if (!File.Exists(path)) return null;
        using var file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (file.Length > MaximumFileBytes) throw new InvalidDataException("The private authoring record is oversized.");
        byte[] bytes = new byte[MaximumFileBytes + 1];
        int used = 0, count;
        while (used < bytes.Length && (count = file.Read(bytes, used, bytes.Length - used)) != 0) used += count;
        if (used > MaximumFileBytes) throw new InvalidDataException("The private authoring record is oversized.");
        try { return DecodeStored(bytes.AsSpan(0, used), path, owner, requestId); }
        finally { CryptographicOperations.ZeroMemory(bytes); }
    }

    private static StoredJob DecodeStored(ReadOnlySpan<byte> bytes, string path, string owner, string? requestId)
    {
        var stored = JsonSerializer.Deserialize<StoredJob>(bytes, Json);
        if (stored is null || stored.Schema != Schema || stored.OwnerDigest != owner
            || stored.Job is not { } job || !ValidId(job.RequestId) || requestId is not null && job.RequestId != requestId
            || stored.Digest != StoredDigest(job, stored.ExecutionAdmission)
            || Path.GetFileNameWithoutExtension(path) != WorkId(owner, job.RequestId)
            || stored.ExecutionAdmission is not null && (!ValidId(stored.ExecutionAdmission)
                || job.State == OriginChapterAuthoringStates.AwaitingAuthoring)
            || job.SourceDigest != OriginChapterSourceIdentity.Digest(job.Source) || job.Provider != "first_book_ai"
            || job.ReaderAcceptedTextDigest is not null && (job.State != OriginChapterAuthoringStates.ReviewRequired
                || job.DraftText is null || job.ReaderAcceptedTextDigest != TextDigest(job.DraftText))
            || job.State is not (OriginChapterAuthoringStates.AwaitingAuthoring
                or OriginChapterAuthoringStates.ReconciliationRequired or OriginChapterAuthoringStates.ReviewRequired)
            || (job.State == OriginChapterAuthoringStates.ReviewRequired
                ? string.IsNullOrWhiteSpace(job.DraftText) || Encoding.UTF8.GetByteCount(job.DraftText) > MaximumDraftBytes || !IsDigest(job.ProviderReceiptDigest)
                : job.DraftText is not null || job.ProviderReceiptDigest is not null))
            throw new InvalidDataException("The private authoring record is invalid.");
        return stored;
    }

    private void Write(string path, string owner, OriginChapterAuthoringJob job, string? executionAdmission = null)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(
            new StoredJob(Schema, owner, job, StoredDigest(job, executionAdmission), executionAdmission), Json);
        try
        {
            if (bytes.Length > MaximumFileBytes) throw new InvalidDataException("The private authoring record is oversized.");
            if (_primarySession is not null)
            {
                _primarySession.Write(Path.GetFileNameWithoutExtension(path), bytes);
                return;
            }
            string temporary = path + ".tmp-" + Guid.NewGuid().ToString("N");
            try
            {
                using (var file = OpenPrivate(temporary, FileMode.CreateNew)) { file.Write(bytes); file.Flush(true); }
                RejectLink(path);
                File.Move(temporary, path, overwrite: true);
            }
            finally { if (File.Exists(temporary)) File.Delete(temporary); }
        }
        finally { CryptographicOperations.ZeroMemory(bytes); }
    }

    private static FileStream OpenPrivate(string path, FileMode mode)
    {
        var options = new FileStreamOptions { Mode = mode, Access = FileAccess.ReadWrite, Share = FileShare.None };
        if (!OperatingSystem.IsWindows()) options.UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
        return new(path, options);
    }

    private static void RequireId(string? value)
    {
        if (!ValidId(value))
            throw new ArgumentException("The authoring identity is invalid.");
    }
    private static bool ValidId(string? value) => !string.IsNullOrWhiteSpace(value) && value.Length <= 256
        && value == value.Trim() && !value.Any(char.IsControl);
    private static string StoredDigest(OriginChapterAuthoringJob job, string? admission)
        => admission is null ? Digest(job) : Digest(new { Job = job, ExecutionAdmission = admission });
    private static string WorkId(string owner, string request) => owner + "." + Digest(request);
    private StoredJob ReadWorkerRecord(string root, string workId)
    {
        if (workId is not { Length: 129 } || workId[64] != '.' || !IsDigest(workId[..64]) || !IsDigest(workId[65..]))
            throw new ArgumentException("The worker identity is invalid.");
        return ReadStored(Path.Combine(root, workId + ".json"), workId[..64], null) ?? throw new KeyNotFoundException();
    }
    private static OriginChapterWorkerItem WorkerItem(StoredJob stored)
        => new(WorkId(stored.OwnerDigest, stored.Job.RequestId), stored.Job, stored.ExecutionAdmission,
            Digest(new { Scope = "origin-reader-book/v1", stored.OwnerDigest,
                stored.Job.Source.WorkspaceId, stored.Job.Source.Locale }));
    private static string Owner(string subject) { RequireId(subject); return Digest(subject); }
    private static string JobPath(string root, string owner, string request) { RequireId(request); return Path.Combine(root, owner + "." + Digest(request) + ".json"); }
    private static string Digest<T>(T value) => Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(value, Json))).ToLowerInvariant();
    private static string TextDigest(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
    private static bool IsDigest(string? value) => value is { Length: 64 } && value.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');
    private static void RejectLink(string path)
    {
        if (new FileInfo(path).LinkTarget is not null || new DirectoryInfo(path).LinkTarget is not null)
            throw new IOException("Linked private authoring storage is not allowed.");
    }
}

// Private worker API DTOs, not public package contracts or provider account data.
public sealed record OriginChapterWorkerItem(string WorkId, OriginChapterAuthoringJob Job, string? ExecutionAdmission,
    string BookRef);
public sealed record OriginChapterWorkerAdmission(OriginChapterWorkerItem Work, bool MayStartGeneration);
