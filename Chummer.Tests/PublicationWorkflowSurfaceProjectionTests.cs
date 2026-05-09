using Chummer.Run.Contracts.Publication;
using Chummer.Run.Registry.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicationWorkflowSurfaceProjectionTests
{
    [Fact]
    public void PublishedPublicationProjectsFirstPartyRoutesAndModeratedProofRefs()
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

        Assert.NotNull(published.SurfaceRoutes);
        Assert.Equal($"/artifacts/publications/{published.PublicationId}", published.SurfaceRoutes!.PublicShelfRoute);
        Assert.Equal($"/artifacts/publications/{published.PublicationId}/concierge", published.SurfaceRoutes.CreatorConciergeRoute);
        Assert.Equal($"/testimonials/concierge?publicationId={published.PublicationId}", published.SurfaceRoutes.TestimonialConciergeRoute);
        Assert.Equal($"/account/work/publications/{published.PublicationId}", published.SurfaceRoutes.SignedInShelfRoute);

        Assert.NotNull(published.MediaAssetRefs);
        Assert.Equal("published", published.MediaAssetRefs!.ModerationState);
        Assert.NotNull(published.MediaAssetRefs.ModeratedAtUtc);
        Assert.Equal($"/artifacts/publications/{published.PublicationId}", published.MediaAssetRefs.CreatorAssetRefs!["public-shelf"]);
        Assert.Equal($"/artifacts/publications/{published.PublicationId}/concierge", published.MediaAssetRefs.CreatorAssetRefs["creator-concierge"]);
        Assert.Equal($"/account/work/publications/{published.PublicationId}", published.MediaAssetRefs.CreatorAssetRefs["signed-in-shelf"]);
        Assert.Equal($"public-shelf:/artifacts/publications/{published.PublicationId}", published.MediaAssetRefs.ModeratedPublicProofAssetRefs!["route-receipt"]);
        Assert.Equal($"registry://publications/{published.PublicationId}/trust", published.MediaAssetRefs.ModeratedPublicProofAssetRefs["trust-projection"]);
        Assert.Equal($"/testimonials/concierge?publicationId={published.PublicationId}", published.MediaAssetRefs.ModeratedPublicProofAssetRefs["testimonial-concierge"]);
    }
}
