using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

/// <summary>
/// Durable private authoring requests. Does not execute a provider or reserve
/// credits. A worker must separately obtain execution/quota authority. The
/// durable dispatch fence is never automatically reset after a lost response.
/// </summary>
public sealed class OriginChapterAuthoringService(IConfiguration configuration)
{
    public const int MaximumRequestBytes = 64 * 1024;
    public const int MaximumDraftBytes = 64 * 1024;
    private const int MaximumFileBytes = 512 * 1024;
    private const string Schema = "chummer.origin.chapter-job/v1";
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { MaxDepth = 16 };
    private readonly object _gate = new();
    private sealed record StoredJob(string Schema, string OwnerDigest, OriginChapterAuthoringJob Job, string Digest);

    public bool IsConfigured => !string.IsNullOrWhiteSpace(configuration["CHUMMER_RUNTIME_STATE_ROOT"]);

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
            if (Directory.EnumerateFiles(root, owner + ".*.json").Take(128).Count() >= 128
                || Directory.EnumerateFiles(root, "*.json").Take(2048).Count() >= 2048)
                throw new InvalidOperationException("The private authoring queue is full.");
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
        if (string.IsNullOrWhiteSpace(draftText) || Encoding.UTF8.GetByteCount(draftText) > MaximumDraftBytes
            || !IsDigest(providerReceiptDigest)) throw new ArgumentException("The chapter result is invalid or oversized.");
        return Locked(root =>
        {
            string owner = Owner(subjectId);
            string path = JobPath(root, owner, requestId);
            var job = Read(path, owner, requestId) ?? throw new KeyNotFoundException();
            if (job.SourceDigest != sourceDigest) throw new InvalidOperationException("The authoring source changed.");
            if (job.State == OriginChapterAuthoringStates.ReviewRequired)
            {
                if (job.DraftText != draftText || job.ProviderReceiptDigest != providerReceiptDigest)
                    throw new InvalidOperationException("A retained chapter result cannot be replaced.");
                return job;
            }
            if (job.State != OriginChapterAuthoringStates.ReconciliationRequired)
                throw new InvalidOperationException("This authoring request was not dispatched.");
            var result = job with { State = OriginChapterAuthoringStates.ReviewRequired,
                DraftText = draftText, ProviderReceiptDigest = providerReceiptDigest };
            Write(path, owner, result);
            return result;
        });
    }

    public int EraseForSubject(string subjectId)
    {
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
        string root = Path.GetFullPath(Path.Combine(configuration["CHUMMER_RUNTIME_STATE_ROOT"]!, "origin-chapter-jobs"));
        lock (_gate)
        {
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

    private static OriginChapterAuthoringJob? Read(string path, string owner, string requestId)
    {
        RejectLink(path);
        if (!File.Exists(path)) return null;
        using var file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (file.Length > MaximumFileBytes) throw new InvalidDataException("The private authoring record is oversized.");
        byte[] bytes = new byte[MaximumFileBytes + 1];
        int used = 0, count;
        while (used < bytes.Length && (count = file.Read(bytes, used, bytes.Length - used)) != 0) used += count;
        if (used > MaximumFileBytes) throw new InvalidDataException("The private authoring record is oversized.");
        var stored = JsonSerializer.Deserialize<StoredJob>(bytes.AsSpan(0, used), Json);
        if (stored is null || stored.Schema != Schema || stored.OwnerDigest != owner
            || stored.Job is not { } job || job.RequestId != requestId || stored.Digest != Digest(job)
            || job.SourceDigest != OriginChapterSourceIdentity.Digest(job.Source) || job.Provider != "first_book_ai"
            || job.State is not (OriginChapterAuthoringStates.AwaitingAuthoring
                or OriginChapterAuthoringStates.ReconciliationRequired or OriginChapterAuthoringStates.ReviewRequired)
            || (job.State == OriginChapterAuthoringStates.ReviewRequired
                ? string.IsNullOrWhiteSpace(job.DraftText) || Encoding.UTF8.GetByteCount(job.DraftText) > MaximumDraftBytes || !IsDigest(job.ProviderReceiptDigest)
                : job.DraftText is not null || job.ProviderReceiptDigest is not null))
            throw new InvalidDataException("The private authoring record is invalid.");
        return job;
    }

    private static void Write(string path, string owner, OriginChapterAuthoringJob job)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(new StoredJob(Schema, owner, job, Digest(job)), Json);
        if (bytes.Length > MaximumFileBytes) throw new InvalidDataException("The private authoring record is oversized.");
        string temporary = path + ".tmp-" + Guid.NewGuid().ToString("N");
        try
        {
            using (var file = OpenPrivate(temporary, FileMode.CreateNew)) { file.Write(bytes); file.Flush(true); }
            RejectLink(path);
            File.Move(temporary, path, overwrite: true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    private static FileStream OpenPrivate(string path, FileMode mode)
    {
        var options = new FileStreamOptions { Mode = mode, Access = FileAccess.ReadWrite, Share = FileShare.None };
        if (!OperatingSystem.IsWindows()) options.UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
        return new(path, options);
    }

    private static void RequireId(string? value)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length > 256 || value != value.Trim() || value.Any(char.IsControl))
            throw new ArgumentException("The authoring identity is invalid.");
    }
    private static string Owner(string subject) { RequireId(subject); return Digest(subject); }
    private static string JobPath(string root, string owner, string request) { RequireId(request); return Path.Combine(root, owner + "." + Digest(request) + ".json"); }
    private static string Digest<T>(T value) => Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(value, Json))).ToLowerInvariant();
    private static bool IsDigest(string? value) => value is { Length: 64 } && value.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');
    private static void RejectLink(string path)
    {
        if (new FileInfo(path).LinkTarget is not null || new DirectoryInfo(path).LinkTarget is not null)
            throw new IOException("Linked private authoring storage is not allowed.");
    }
}
