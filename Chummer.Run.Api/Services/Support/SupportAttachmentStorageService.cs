using Chummer.Control.Contracts.Support;
using Chummer.Storage.Teable;
using System.Security.Cryptography;
using System.Text.Json;

namespace Chummer.Run.Api.Services.Support;

public sealed class SupportAttachmentStorageService
{
    public const int MaxAttachmentCount = 5;
    public const int MaxAttachmentBytes = 8 * 1024 * 1024;
    public const long MaxMultipartBodyBytes = ((long)MaxAttachmentCount * MaxAttachmentBytes) + (256 * 1024);

    private static readonly HashSet<string> AllowedExtensions =
    [
        ".txt",
        ".log",
        ".json",
        ".zip",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".md"
    ];

    private readonly string _attachmentRoot;
    private readonly SupportStore? _store;
    private readonly TeableRevisionStore? _primary;
    private const string PrimarySchema = "chummer.hub.support-attachment/v1";
    private const int MaximumPrimaryBytes = 12 * 1024 * 1024;
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private sealed record PrimaryAttachment(string Schema, string CaseId,
        SupportCaseAttachmentProjection Metadata, byte[] Content);
    internal bool UsesStore(SupportStore store) => store.IsPrimary ? ReferenceEquals(_store, store) : _primary is null;

    public SupportAttachmentStorageService(IConfiguration configuration, SupportStore? store = null)
    {
        string mode = configuration["CHUMMER_SUPPORT_STORAGE_PROVIDER"]?.Trim() ?? "local";
        if (mode is not ("local" or "teable") || (mode == "teable") != (store?.IsPrimary == true))
            throw new InvalidOperationException("Support attachments require the same explicit primary store as support cases.");
        _store = store?.IsPrimary == true ? store : null;
        _primary = _store?.Primary;
        _attachmentRoot = _primary is null ? ResolveAttachmentRoot(configuration) : string.Empty;
    }

    public IReadOnlyList<SupportCaseAttachmentProjection> SaveAttachments(
        string caseId,
        IReadOnlyList<SupportAttachmentUpload> attachments)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(caseId);
        ArgumentNullException.ThrowIfNull(attachments);

        if (attachments.Count == 0)
        {
            return Array.Empty<SupportCaseAttachmentProjection>();
        }

        if (attachments.Count > MaxAttachmentCount)
        {
            throw new ArgumentException("Support intake accepts up to five attachments per case.");
        }

        if (_primary is not null) return SavePrimaryAttachments(caseId, attachments);

        string caseDirectory = Path.Combine(_attachmentRoot, caseId.Trim());
        Directory.CreateDirectory(caseDirectory);
        List<SupportCaseAttachmentProjection> saved = new(attachments.Count);

        foreach (var attachment in attachments)
        {
            if (attachment.Content.Length == 0)
            {
                continue;
            }

            if (attachment.Content.Length > MaxAttachmentBytes)
            {
                throw new ArgumentException($"Attachment '{attachment.FileName}' exceeds the 8 MB limit.");
            }

            string safeName = SanitizeFileName(attachment.FileName);
            string extension = Path.GetExtension(safeName);
            if (string.IsNullOrWhiteSpace(extension) || !AllowedExtensions.Contains(extension))
            {
                throw new ArgumentException($"Attachment '{attachment.FileName}' uses an unsupported file type.");
            }

            string attachmentId = $"support_att_{Guid.NewGuid():N}"[..24];
            string storedName = $"{attachmentId}_{safeName}";
            string storedPath = Path.Combine(caseDirectory, storedName);
            File.WriteAllBytes(storedPath, attachment.Content);

            saved.Add(new SupportCaseAttachmentProjection(
                AttachmentId: attachmentId,
                FileName: safeName,
                ContentType: string.IsNullOrWhiteSpace(attachment.ContentType) ? "application/octet-stream" : attachment.ContentType.Trim(),
                SizeBytes: attachment.Content.Length,
                UploadedAtUtc: DateTimeOffset.UtcNow));
        }

        return saved;
    }

    public (Stream Stream, string FileName, string ContentType)? TryOpenAttachment(string caseId, string attachmentId)
    {
        if (string.IsNullOrWhiteSpace(caseId) || string.IsNullOrWhiteSpace(attachmentId))
        {
            return null;
        }

        if (_primary is not null) return OpenPrimaryAttachment(caseId, attachmentId);

        string caseDirectory = Path.Combine(_attachmentRoot, caseId.Trim());
        if (!Directory.Exists(caseDirectory))
        {
            return null;
        }

        string prefix = $"{attachmentId.Trim()}_";
        string? match = Directory.EnumerateFiles(caseDirectory, $"{prefix}*").OrderBy(static path => path, StringComparer.OrdinalIgnoreCase).FirstOrDefault();
        if (match is null)
        {
            return null;
        }

        string fileName = Path.GetFileName(match)[prefix.Length..];
        return (File.OpenRead(match), fileName, ContentTypeForFileName(fileName));
    }

    private static string ContentTypeForFileName(string fileName)
        => Path.GetExtension(fileName).ToLowerInvariant() switch
        {
            ".txt" or ".log" or ".md" => "text/plain",
            ".json" => "application/json",
            ".zip" => "application/zip",
            ".png" => "image/png",
            ".jpg" or ".jpeg" => "image/jpeg",
            ".webp" => "image/webp",
            _ => "application/octet-stream"
        };

    private IReadOnlyList<SupportCaseAttachmentProjection> SavePrimaryAttachments(
        string caseId, IReadOnlyList<SupportAttachmentUpload> attachments)
    {
        using var scope = _store!.Enter();
        // Validate the entire batch before storing any bytes. Blobs are immutable
        // revision-1 objects; only a committed support-case reference exposes them.
        var pending = new List<PrimaryAttachment>();
        foreach (var upload in attachments)
        {
            if (upload is null || upload.Content is null) throw new ArgumentException("Attachment content is required.");
            if (upload.Content.Length == 0) continue;
            string fileName = SanitizeFileName(upload.FileName);
            if (upload.Content.Length > MaxAttachmentBytes || fileName.Length > 255
                || !AllowedExtensions.Contains(Path.GetExtension(fileName)))
                throw new ArgumentException("Attachment size or file type is unsupported.");
            string contentType = string.IsNullOrWhiteSpace(upload.ContentType) ? "application/octet-stream" : upload.ContentType.Trim();
            if (contentType.Length > 256 || contentType.Any(char.IsControl))
                throw new ArgumentException("Attachment content type is invalid.");
            var metadata = new SupportCaseAttachmentProjection($"support_att_{Guid.NewGuid():N}"[..24],
                fileName, contentType, upload.Content.Length, DateTimeOffset.UtcNow);
            pending.Add(new(PrimarySchema, caseId.Trim(), metadata, upload.Content));
        }
        foreach (var attachment in pending)
        {
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(attachment, Json);
            TeableRevisionStore.Head? written = null;
            try
            {
                if (bytes.Length > MaximumPrimaryBytes) throw new InvalidDataException("Attachment primary payload is oversized.");
                using var deadline = new CancellationTokenSource(TimeSpan.FromMinutes(2));
                written = _primary!.CompareExchangeAsync(AttachmentStream(caseId, attachment.Metadata.AttachmentId),
                    null, Guid.NewGuid(), bytes, deadline.Token).GetAwaiter().GetResult();
            }
            finally
            {
                CryptographicOperations.ZeroMemory(bytes);
                if (written is not null) CryptographicOperations.ZeroMemory(written.Bytes);
            }
        }
        return pending.Select(item => item.Metadata).ToArray();
    }

    private (Stream Stream, string FileName, string ContentType)? OpenPrimaryAttachment(string caseId, string attachmentId)
    {
        using var scope = _store!.Enter();
        if (!_store.CasesById.TryGetValue(caseId.Trim(), out var supportCase)) return null;
        var metadata = supportCase.Attachments?.SingleOrDefault(item =>
            string.Equals(item.AttachmentId, attachmentId.Trim(), StringComparison.OrdinalIgnoreCase));
        if (metadata is null) return null; // Orphan blob is not a downloadable case attachment.
        using var deadline = new CancellationTokenSource(TimeSpan.FromMinutes(2));
        var head = _primary!.ReadAsync(AttachmentStream(caseId, attachmentId), deadline.Token).GetAwaiter().GetResult();
        try
        {
            if (head is null || head.Revision != 1 || head.Bytes.Length > MaximumPrimaryBytes)
                throw new InvalidDataException("Support attachment primary authority is missing or mutable.");
            var attachment = JsonSerializer.Deserialize<PrimaryAttachment>(head.Bytes, Json);
            if (attachment is not { Schema: PrimarySchema, Metadata: not null, Content: not null }
                || !string.Equals(attachment.CaseId, caseId.Trim(), StringComparison.OrdinalIgnoreCase)
                || attachment.Metadata != (metadata with { DownloadHref = null })
                || attachment.Content.Length != metadata.SizeBytes
                || attachment.Content.Length is < 1 or > MaxAttachmentBytes)
                throw new InvalidDataException("Support attachment primary binding is invalid.");
            return (new MemoryStream(attachment.Content, writable: false), metadata.FileName, ContentTypeForFileName(metadata.FileName));
        }
        finally { if (head is not null) CryptographicOperations.ZeroMemory(head.Bytes); }
    }

    private static string AttachmentStream(string caseId, string attachmentId)
    {
        if (new[] { caseId, attachmentId }.Any(value => string.IsNullOrWhiteSpace(value) || value.Length > 128 || value.Any(char.IsControl)))
            throw new ArgumentException("Support attachment identity is invalid.");
        byte[] identity = JsonSerializer.SerializeToUtf8Bytes(new[] { caseId.Trim().ToUpperInvariant(), attachmentId.Trim().ToUpperInvariant() });
        try { return "support-attachment-" + Convert.ToHexStringLower(SHA256.HashData(identity)); }
        finally { CryptographicOperations.ZeroMemory(identity); }
    }

    private static string ResolveAttachmentRoot(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_SUPPORT_ATTACHMENT_ROOT"] ?? configuration["Support:AttachmentRoot"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(Path.GetTempPath(), "chummer6-hub", "support-attachments");
    }

    private static string SanitizeFileName(string? fileName)
    {
        string raw = string.IsNullOrWhiteSpace(fileName) ? "attachment.bin" : fileName.Trim();
        var invalid = Path.GetInvalidFileNameChars();
        Span<char> buffer = stackalloc char[raw.Length];
        int index = 0;
        foreach (char ch in raw)
        {
            buffer[index++] = invalid.Contains(ch) ? '_' : ch;
        }

        string sanitized = new string(buffer[..index]).Replace(' ', '-');
        return string.IsNullOrWhiteSpace(sanitized) ? "attachment.bin" : sanitized;
    }
}

public sealed record SupportAttachmentUpload(
    string FileName,
    string ContentType,
    byte[] Content);
