using Chummer.Run.Contracts.Publication;
using Chummer.Run.Registry.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicationWorkflowSurfaceProjectionTests
{
    [Fact]
    public void PublishedPublicationProjectsTrustAndModerationProjections()
    {
        PublicationWorkflowService workflow = new();

        PublicationRecordResponse created = workflow.Submit(new PublicationSubmissionRequest(
            ArtifactId: "artifact_publication_surface_demo",
            ArtifactKind: "RulePack",
            Title: "Surface projection demo",
            SubmittedBy: "author.demo",
            Notes: "surface projection proof"));
        PublicationMutationResult reviewed = workflow.Review(created.PublicationId, new PublicationReviewRequest(
            Reviewer: "moderator.demo",
            Approved: true,
            Notes: "approval-backed"), created.ConcurrencyToken);
        PublicationRecordResponse published = workflow.Publish(created.PublicationId, new PublicationPublishRequest(
            PublishedBy: "publisher.demo",
            Notes: "live"), reviewed.Publication!.ConcurrencyToken).Publication
            ?? throw new InvalidOperationException("Expected a published projection.");

        Assert.NotNull(published.TrustProjection);
        Assert.True(published.TrustProjection!.Discoverable);
        Assert.Equal("curated-live", published.TrustProjection.RankingBand);
        Assert.Contains("shared visibility", published.TrustProjection.TrustSummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("discovery", published.TrustProjection.DiscoverySummary, StringComparison.OrdinalIgnoreCase);

        Assert.Equal("published", published.ModerationTimeline.CurrentStage);
        Assert.Equal("moderation-watch", published.ModerationTimeline.PendingDecision);
        Assert.False(published.ModerationTimeline.OperatorAttentionRequired);
        Assert.Contains("Published artifacts remain visible", published.ModerationTimeline.ProjectionReason, StringComparison.Ordinal);

        Assert.Equal(3, published.ApprovalAuditTrail.Count);
        Assert.Collection(
            published.ApprovalAuditTrail,
            submitted => Assert.Equal("submitted", submitted.Outcome),
            reviewed => Assert.Equal("approved", reviewed.Outcome),
            publishedEntry =>
            {
                Assert.Equal("published", publishedEntry.Outcome);
                Assert.True(publishedEntry.ApprovalBacked);
            });
    }
}
