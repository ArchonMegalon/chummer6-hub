using Chummer.Media.Contracts;
using Chummer.Run.Contracts.Media;
using Chummer.Run.AI.Services.Assets;
using System.Collections.Concurrent;
using System.Text;
using System.Net;

namespace Chummer.Run.AI.Services.Creative;

#pragma warning disable CS0618
public interface IPacketFactoryService
{
    Task<PacketFactoryResult> CreateAsync(PacketFactoryRequest request, CancellationToken cancellationToken = default);
    PacketFactoryResult? Get(string packetId);
    Task<IReadOnlyList<PacketAttachmentRecord>> AttachAsync(string packetId, PacketAttachmentBatchRequest request, CancellationToken cancellationToken = default);
}

public sealed class PacketFactoryService : IPacketFactoryService
{
    private sealed class PacketState
    {
        public required string PacketId { get; init; }
        public required string Title { get; init; }
        public required string Subject { get; init; }
        public required string Html { get; init; }
        public required List<string> Evidence { get; init; }
        public required Dictionary<PacketArtifactRole, PacketArtifactHandle> Artifacts { get; init; }
        public required List<PacketAttachmentState> Attachments { get; init; }
    }

    private sealed class PacketAttachmentState
    {
        public required string AttachmentId { get; init; }
        public required PacketAttachmentTargetKind TargetKind { get; init; }
        public required string TargetId { get; init; }
        public string? TargetLabel { get; init; }
        public required DateTimeOffset AttachedAtUtc { get; init; }
    }

    private readonly IMediaRenderJobService _mediaRenderJobs;
    private readonly ConcurrentDictionary<string, PacketState> _packets = new(StringComparer.OrdinalIgnoreCase);
    private readonly object _sync = new();

    public PacketFactoryService(IMediaRenderJobService mediaRenderJobs)
    {
        _mediaRenderJobs = mediaRenderJobs;
    }

    public async Task<PacketFactoryResult> CreateAsync(PacketFactoryRequest request, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(request.Title))
        {
            throw new ArgumentException("Title is required.");
        }

        var packetId = Guid.NewGuid().ToString("N");
        var referenceText = request.References is null || request.References.Count == 0
            ? "No external references were passed."
            : string.Join(", ", request.References);

        var html = BuildHtml(request.Title, request.Subject, referenceText);
        var evidence = new List<string>
        {
            $"references={request.References?.Count ?? 0}",
            $"attachments={request.Attachments?.Count ?? 0}"
        };

        var previewJob = await _mediaRenderJobs.EnqueueAsync(
            new MediaRenderJobEnqueueRequest(
                JobType: MediaRenderJobType.DocumentPreviewImage,
                DeduplicationKey: $"packet-preview::{packetId}",
                Category: "packet/preview",
                Payload: html,
                Source: packetId,
                CacheTtl: TimeSpan.FromDays(30),
                MaxBytes: 2_000_000,
                RequiresApproval: true,
                PersistOnApproval: true,
                AllowPersistentPinning: true),
            cancellationToken);

        var pdfJob = await _mediaRenderJobs.EnqueueAsync(
            new MediaRenderJobEnqueueRequest(
                JobType: MediaRenderJobType.DocumentPdf,
                DeduplicationKey: $"packet-pdf::{packetId}",
                Category: "packet/pdf",
                Payload: BuildPdfPayload(packetId, request.Title, request.Subject, html, referenceText),
                Source: packetId,
                CacheTtl: TimeSpan.FromDays(30),
                MaxBytes: 4_000_000,
                RequiresApproval: true,
                PersistOnApproval: true,
                AllowPersistentPinning: true),
            cancellationToken);

        var thumbnailJob = await _mediaRenderJobs.EnqueueAsync(
            new MediaRenderJobEnqueueRequest(
                JobType: MediaRenderJobType.DocumentThumbnailImage,
                DeduplicationKey: $"packet-thumbnail::{packetId}",
                Category: "packet/thumbnail",
                Payload: BuildThumbnailPayload(request.Title, request.Subject),
                Source: packetId,
                CacheTtl: TimeSpan.FromDays(30),
                MaxBytes: 1_000_000,
                RequiresApproval: true,
                PersistOnApproval: true,
                AllowPersistentPinning: true),
            cancellationToken);

        var packet = new PacketState
        {
            PacketId = packetId,
            Title = request.Title.Trim(),
            Subject = request.Subject.Trim(),
            Html = html,
            Evidence = evidence,
            Artifacts = new Dictionary<PacketArtifactRole, PacketArtifactHandle>
            {
                [PacketArtifactRole.Preview] = ToArtifact(PacketArtifactRole.Preview, "packet/preview", previewJob),
                [PacketArtifactRole.Pdf] = ToArtifact(PacketArtifactRole.Pdf, "packet/pdf", pdfJob),
                [PacketArtifactRole.Thumbnail] = ToArtifact(PacketArtifactRole.Thumbnail, "packet/thumbnail", thumbnailJob)
            },
            Attachments = new List<PacketAttachmentState>()
        };

        _packets[packetId] = packet;

        if (request.Attachments is { Count: > 0 })
        {
            await AttachAsync(packetId, new PacketAttachmentBatchRequest(request.Attachments), cancellationToken);
        }

        return BuildResult(packet);
    }

    public PacketFactoryResult? Get(string packetId)
    {
        if (string.IsNullOrWhiteSpace(packetId) || !_packets.TryGetValue(packetId.Trim(), out var packet))
        {
            return null;
        }

        return BuildResult(packet);
    }

    public Task<IReadOnlyList<PacketAttachmentRecord>> AttachAsync(
        string packetId,
        PacketAttachmentBatchRequest request,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (request.Attachments is null || request.Attachments.Count == 0)
        {
            throw new ArgumentException("At least one attachment is required.", nameof(request));
        }

        if (!_packets.TryGetValue(packetId.Trim(), out var packet))
        {
            throw new KeyNotFoundException($"Packet '{packetId}' was not found.");
        }

        lock (_sync)
        {
            foreach (var attachment in request.Attachments)
            {
                var normalized = NormalizeAttachment(attachment);
                if (packet.Attachments.Any(existing =>
                        existing.TargetKind == normalized.TargetKind &&
                        string.Equals(existing.TargetId, normalized.TargetId, StringComparison.OrdinalIgnoreCase)))
                {
                    continue;
                }

                packet.Attachments.Add(new PacketAttachmentState
                {
                    AttachmentId = $"pkt_attach_{Guid.NewGuid():N}",
                    TargetKind = normalized.TargetKind,
                    TargetId = normalized.TargetId,
                    TargetLabel = normalized.TargetLabel,
                    AttachedAtUtc = DateTimeOffset.UtcNow
                });
            }

            return Task.FromResult<IReadOnlyList<PacketAttachmentRecord>>(BuildAttachments(packet));
        }
    }

    private static string BuildHtml(string title, string subject, string references)
    {
        var safeTitle = WebUtility.HtmlEncode(title);
        var safeSubject = WebUtility.HtmlEncode(subject);
        var body = new StringBuilder()
            .Append("<html><head><meta charset='utf-8' />")
            .Append($"<title>{safeTitle}</title></head><body>")
            .Append($"<h1>{safeTitle}</h1>")
            .Append($"<p><strong>{safeSubject}</strong></p>")
            .Append($"<p>{references}</p>")
            .Append("</body></html>")
            .ToString();

        return body;
    }

    private PacketFactoryResult BuildResult(PacketState packet)
    {
        var artifacts = packet.Artifacts
            .Keys
            .OrderBy(static role => role)
            .Select(role => RefreshArtifact(packet.Artifacts[role]))
            .ToArray();

        var preview = artifacts.FirstOrDefault(static artifact => artifact.Role == PacketArtifactRole.Preview);
        var pdf = artifacts.FirstOrDefault(static artifact => artifact.Role == PacketArtifactRole.Pdf);
        var thumbnail = artifacts.FirstOrDefault(static artifact => artifact.Role == PacketArtifactRole.Thumbnail);

        return new PacketFactoryResult(
            PacketId: packet.PacketId,
            Title: packet.Title,
            Subject: packet.Subject,
            Html: packet.Html,
            PreviewAssetId: preview?.AssetId,
            PdfAssetId: pdf?.AssetId,
            ThumbnailAssetId: thumbnail?.AssetId,
            Artifacts: artifacts,
            Attachments: BuildAttachments(packet),
            Evidence: packet.Evidence);
    }

    private IReadOnlyList<PacketAttachmentRecord> BuildAttachments(PacketState packet)
    {
        var artifacts = packet.Artifacts
            .Keys
            .OrderBy(static role => role)
            .Select(role => RefreshArtifact(packet.Artifacts[role]))
            .ToArray();

        return packet.Attachments
            .OrderBy(static attachment => attachment.AttachedAtUtc)
            .Select(attachment => new PacketAttachmentRecord(
                AttachmentId: attachment.AttachmentId,
                PacketId: packet.PacketId,
                TargetKind: attachment.TargetKind,
                TargetId: attachment.TargetId,
                TargetLabel: attachment.TargetLabel,
                AttachedAtUtc: attachment.AttachedAtUtc,
                Artifacts: artifacts))
            .ToArray();
    }

    private PacketArtifactHandle RefreshArtifact(PacketArtifactHandle artifact)
    {
        var status = _mediaRenderJobs.Get(artifact.JobId);
        if (status is null)
        {
            return artifact;
        }

        return artifact with
        {
            JobState = status.State,
            AssetId = status.AssetId,
            CacheTtl = status.CacheTtl
        };
    }

    private static PacketArtifactHandle ToArtifact(PacketArtifactRole role, string category, MediaRenderJobStatus job) =>
        new(
            Role: role,
            Category: category,
            JobId: job.JobId,
            JobState: job.State,
            AssetId: job.AssetId,
            CacheTtl: job.CacheTtl);

    private static PacketAttachmentRequest NormalizeAttachment(PacketAttachmentRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.TargetId))
        {
            throw new ArgumentException("Attachment target id is required.", nameof(request));
        }

        return request with
        {
            TargetId = request.TargetId.Trim(),
            TargetLabel = string.IsNullOrWhiteSpace(request.TargetLabel) ? null : request.TargetLabel.Trim()
        };
    }

    private static string BuildPdfPayload(string packetId, string title, string subject, string html, string references)
    {
        var payload = new StringBuilder()
            .AppendLine("<packet-pdf source=\"markupgo\">")
            .AppendLine($"  <packet-id>{WebUtility.HtmlEncode(packetId)}</packet-id>")
            .AppendLine($"  <title>{WebUtility.HtmlEncode(title)}</title>")
            .AppendLine($"  <subject>{WebUtility.HtmlEncode(subject)}</subject>")
            .AppendLine($"  <references>{WebUtility.HtmlEncode(references)}</references>")
            .AppendLine($"  <html><![CDATA[{html}]]></html>")
            .AppendLine("</packet-pdf>")
            .ToString();

        return payload;
    }

    private static string BuildThumbnailPayload(string title, string subject)
    {
        return $"<packet-thumbnail source=\"peekshot\"><title>{WebUtility.HtmlEncode(title)}</title><subject>{WebUtility.HtmlEncode(subject)}</subject></packet-thumbnail>";
    }
}
#pragma warning restore CS0618
