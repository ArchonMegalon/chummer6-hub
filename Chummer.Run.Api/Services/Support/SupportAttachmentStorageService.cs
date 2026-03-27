using Chummer.Control.Contracts.Support;

namespace Chummer.Run.Api.Services.Support;

public sealed class SupportAttachmentStorageService
{
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

    public SupportAttachmentStorageService(IConfiguration configuration)
    {
        _attachmentRoot = ResolveAttachmentRoot(configuration);
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

        if (attachments.Count > 5)
        {
            throw new ArgumentException("Support intake accepts up to five attachments per case.");
        }

        string caseDirectory = Path.Combine(_attachmentRoot, caseId.Trim());
        Directory.CreateDirectory(caseDirectory);
        List<SupportCaseAttachmentProjection> saved = new(attachments.Count);

        foreach (var attachment in attachments)
        {
            if (attachment.Content.Length == 0)
            {
                continue;
            }

            if (attachment.Content.Length > 8 * 1024 * 1024)
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
        string extension = Path.GetExtension(fileName).ToLowerInvariant();
        string contentType = extension switch
        {
            ".txt" or ".log" or ".md" => "text/plain",
            ".json" => "application/json",
            ".zip" => "application/zip",
            ".png" => "image/png",
            ".jpg" or ".jpeg" => "image/jpeg",
            ".webp" => "image/webp",
            _ => "application/octet-stream"
        };

        return (File.OpenRead(match), fileName, contentType);
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
