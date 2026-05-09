using Chummer.Media.Contracts;
using Chummer.Run.AI.Services.Assets;
using Xunit;

namespace Chummer.Tests;

public sealed class ModeratedTestimonialRenderingServiceTests
{
    [Fact]
    public async Task RenderAsyncProducesScopedReceiptsAndReadyRefs()
    {
        IAssetLifecycleService assets = new AssetLifecycleService();
        IMediaRenderJobService jobs = new MediaRenderJobService(assets);
        IModeratedTestimonialRenderingService service = new ModeratedTestimonialRenderingService(jobs);

        var request = new ModeratedTestimonialRenderRequest(
            RenderingId: "testimonial-render-demo-001",
            PublicationId: "publication-demo-001",
            ModerationCaseId: "moderation-case-demo-001",
            SourceReceiptId: "source-receipt-demo-001",
            ConsentReceiptId: "consent-receipt-demo-001",
            Source: "xunit",
            RequestedAtUtc: DateTimeOffset.Parse("2026-05-09T09:00:00Z"),
            Artifacts:
            [
                BuildArtifact(
                    ModeratedTestimonialArtifactRole.Video,
                    "testimonial/video",
                    "video/mp4",
                    "asset://testimonial/video",
                    "caption://testimonial/demo",
                    "preview://testimonial/demo"),
                BuildArtifact(
                    ModeratedTestimonialArtifactRole.Audio,
                    "testimonial/audio",
                    "audio/mpeg",
                    "asset://testimonial/audio",
                    "caption://testimonial/demo",
                    null),
                BuildArtifact(
                    ModeratedTestimonialArtifactRole.PreviewCard,
                    "testimonial/preview-card",
                    "image/webp",
                    "asset://testimonial/preview-card",
                    null,
                    "preview://testimonial/demo"),
                BuildArtifact(
                    ModeratedTestimonialArtifactRole.TranscriptCard,
                    "testimonial/transcript-card",
                    "text/html",
                    "asset://testimonial/transcript-card",
                    null,
                    null)
            ]);

        ModeratedTestimonialRenderReceipt receipt = await service.RenderAsync(request);

        Assert.Equal(4, receipt.Artifacts.Count);
        Assert.Equal(4, receipt.ReadyRefs.Count);
        Assert.Equal(4, receipt.ArtifactRefReceipts.Count);
        Assert.Single(receipt.VideoReceiptIds);
        Assert.Single(receipt.AudioReceiptIds);
        Assert.Single(receipt.PreviewCardReceiptIds);
        Assert.Single(receipt.TranscriptCardReceiptIds);
        Assert.Contains(receipt.CaptionRefReceipts, item => string.Equals(item.Ref, "caption://testimonial/demo", StringComparison.Ordinal));
        Assert.Contains(receipt.PreviewRefReceipts, item => string.Equals(item.Ref, "preview://testimonial/demo", StringComparison.Ordinal));
        Assert.All(receipt.Artifacts, item =>
        {
            Assert.Equal(MediaRenderJobState.Succeeded, item.JobState);
            Assert.Equal("pending-review", item.ModerationState);
            Assert.False(string.IsNullOrWhiteSpace(item.AssetId));
            Assert.False(string.IsNullOrWhiteSpace(item.AssetUrl));
        });
    }

    [Fact]
    public async Task RenderAsyncRejectsPayloadOutsideModerationScope()
    {
        IAssetLifecycleService assets = new AssetLifecycleService();
        IMediaRenderJobService jobs = new MediaRenderJobService(assets);
        IModeratedTestimonialRenderingService service = new ModeratedTestimonialRenderingService(jobs);

        var request = new ModeratedTestimonialRenderRequest(
            RenderingId: "testimonial-render-demo-002",
            PublicationId: "publication-demo-002",
            ModerationCaseId: "moderation-case-demo-002",
            SourceReceiptId: "source-receipt-demo-002",
            ConsentReceiptId: "consent-receipt-demo-002",
            Source: "xunit",
            RequestedAtUtc: DateTimeOffset.Parse("2026-05-09T10:00:00Z"),
            Artifacts:
            [
                new ModeratedTestimonialArtifactRenderRequest(
                    Role: ModeratedTestimonialArtifactRole.Video,
                    Category: "testimonial/video",
                    Payload: "{\"publicationId\":\"publication-demo-002\",\"moderationCaseId\":\"moderation-case-demo-002\",\"sourceReceiptId\":\"source-receipt-demo-002\",\"consentReceiptId\":\"wrong-consent\"}",
                    OutputFormat: "video/mp4",
                    AssetRef: "asset://testimonial/video",
                    CaptionRefs: ["caption://testimonial/demo"],
                    PreviewRefs: ["preview://testimonial/demo"],
                    DeduplicationKey: "video")
            ]);

        await Assert.ThrowsAsync<ArgumentException>(() => service.RenderAsync(request));
    }

    private static ModeratedTestimonialArtifactRenderRequest BuildArtifact(
        ModeratedTestimonialArtifactRole role,
        string category,
        string outputFormat,
        string assetRef,
        string? captionRef,
        string? previewRef)
    {
        var payload = $$"""
            {
              "publicationId": "publication-demo-001",
              "moderationCaseId": "moderation-case-demo-001",
              "sourceReceiptId": "source-receipt-demo-001",
              "consentReceiptId": "consent-receipt-demo-001",
              "assetRef": "{{assetRef}}",
              "role": "{{role}}"
            }
            """;

        return new ModeratedTestimonialArtifactRenderRequest(
            Role: role,
            Category: category,
            Payload: payload,
            OutputFormat: outputFormat,
            AssetRef: assetRef,
            CaptionRefs: captionRef is null ? Array.Empty<string>() : [captionRef],
            PreviewRefs: previewRef is null ? Array.Empty<string>() : [previewRef],
            DeduplicationKey: role.ToString().ToLowerInvariant());
    }
}
