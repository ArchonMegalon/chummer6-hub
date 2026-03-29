using Chummer.Run.Registry.Services;
using Chummer.Run.Contracts.Publication;

namespace RunServicesVerification;

internal static class PublicationVerification
{
    public static void Run()
    {
        var workflow = new PublicationWorkflowService();

        var created = workflow.Submit(new PublicationSubmissionRequest(
            ArtifactId: "runtime-bundle:alpha",
            ArtifactKind: "RuntimeBundle",
            Title: "Runtime bundle alpha",
            SubmittedBy: "ops.publisher",
            Notes: "initial hub submission"));

        VerificationAssert.Equal(PublicationState.PendingReview, created.State, "New publications should start pending review.");
        VerificationAssert.True(!string.IsNullOrWhiteSpace(created.ConcurrencyToken), "New publications should expose a concurrency token.");
        VerificationAssert.Equal(1, workflow.List(PublicationState.PendingReview).Count, "List should filter by publication state.");
        VerificationAssert.True(created.ApprovalAuditTrail.Count == 1, "Submissions should initialize an approval audit trail.");
        VerificationAssert.Equal("review", created.ModerationTimeline.PendingDecision, "Pending review publications should project the next review decision.");
        VerificationAssert.True(created.ModerationTimeline.OperatorAttentionRequired, "Pending review publications should require operator attention.");
        VerificationAssert.True(created.ModerationTimeline.NextSafeActionSummary?.Contains("approval review", StringComparison.OrdinalIgnoreCase) == true, "Pending review publications should expose an explicit next safe action summary.");

        var staleReview = workflow.Review(
            created.PublicationId,
            new PublicationReviewRequest("ops.reviewer", Approved: true, Notes: "approve"),
            "\"pub:stale:v9\"");
        VerificationAssert.Equal(PublicationMutationStatus.PreconditionFailed, staleReview.Status, "Review should reject stale concurrency tokens.");

        var approved = workflow.Review(
            created.PublicationId,
            new PublicationReviewRequest("ops.reviewer", Approved: true, Notes: "approve"),
            created.ConcurrencyToken);
        VerificationAssert.Equal(PublicationMutationStatus.Success, approved.Status, "Review should succeed with the current token.");
        VerificationAssert.Equal(PublicationState.Approved, approved.Publication!.State, "Review should transition the publication to approved.");
        VerificationAssert.Equal("publish", approved.Publication.ModerationTimeline.PendingDecision, "Approved publications should project publication as the next decision.");
        VerificationAssert.True(approved.Publication.ModerationTimeline.NextSafeActionSummary?.Contains("Publish the approved artifact", StringComparison.Ordinal) == true, "Approved publications should expose an explicit publish-safe next action summary.");
        VerificationAssert.True(
            approved.Publication.ApprovalAuditTrail.Any(entry => entry.Stage == "approval-review" && entry.Outcome == "approved" && entry.ApprovalBacked),
            "Approved publications should retain approval-backed review receipts.");

        var rejectedWithApprovedPhrase = workflow.Submit(new PublicationSubmissionRequest(
            ArtifactId: "runtime-bundle:gamma",
            ArtifactKind: "RuntimeBundle",
            Title: "Runtime bundle gamma",
            SubmittedBy: "ops.publisher",
            Notes: "verification submission"));
        var rejectedReview = workflow.Review(
            rejectedWithApprovedPhrase.PublicationId,
            new PublicationReviewRequest("ops.reviewer", Approved: false, Notes: "not approved until legal signoff"),
            rejectedWithApprovedPhrase.ConcurrencyToken);
        VerificationAssert.Equal(PublicationMutationStatus.Success, rejectedReview.Status, "Rejected review should still succeed.");
        VerificationAssert.True(
            rejectedReview.Publication!.ApprovalAuditTrail.Any(entry => entry.Stage == "approval-review" && entry.Outcome == "rejected"),
            "Rejected review notes containing 'approved' should remain rejected in the audit trail.");

        var publishConflict = workflow.Publish(
            created.PublicationId,
            new PublicationPublishRequest("ops.publisher", "stale"),
            created.ConcurrencyToken);
        VerificationAssert.Equal(PublicationMutationStatus.PreconditionFailed, publishConflict.Status, "Publish should reject stale tokens.");

        var published = workflow.Publish(
            created.PublicationId,
            new PublicationPublishRequest("ops.publisher", "publish approved artifact"),
            approved.Publication!.ConcurrencyToken);
        VerificationAssert.Equal(PublicationState.Published, published.Publication!.State, "Approved publications should publish.");
        VerificationAssert.True(published.Publication.ImmutableRetentionRequired, "Published artifacts should require immutable retention.");
        VerificationAssert.True(published.Publication.ModerationTimeline.NextSafeActionSummary?.Contains("live published artifact", StringComparison.OrdinalIgnoreCase) == true, "Published publications should expose an explicit moderation-watch next action summary.");

        var delisted = workflow.Moderate(
            created.PublicationId,
            new PublicationModerationRequest("ops.moderator", "delist", Reason: "policy hold"),
            published.Publication.ConcurrencyToken);
        VerificationAssert.Equal(PublicationState.Delisted, delisted.Publication!.State, "Moderation should allow delisting published artifacts.");

        var deprecated = workflow.Moderate(
            created.PublicationId,
            new PublicationModerationRequest("ops.moderator", "deprecate", Reason: "replaced"),
            delisted.Publication!.ConcurrencyToken);
        VerificationAssert.Equal(PublicationState.Deprecated, deprecated.Publication!.State, "Moderation should allow deprecation after delist.");

        var supersedeConflict = workflow.Moderate(
            created.PublicationId,
            new PublicationModerationRequest("ops.moderator", "supersede", Reason: "missing successor"),
            deprecated.Publication!.ConcurrencyToken);
        VerificationAssert.Equal(PublicationMutationStatus.Conflict, supersedeConflict.Status, "Supersede should require replacement metadata.");

        var superseded = workflow.Moderate(
            created.PublicationId,
            new PublicationModerationRequest("ops.moderator", "supersede", SupersededByArtifactId: "runtime-bundle:beta", Reason: "new bundle"),
            deprecated.Publication!.ConcurrencyToken);
        VerificationAssert.Equal(PublicationState.Superseded, superseded.Publication!.State, "Moderation should allow supersede with replacement metadata.");
        VerificationAssert.Equal("runtime-bundle:beta", superseded.Publication.SupersededByArtifactId!, "Superseded publications should carry replacement artifact ids.");
        VerificationAssert.Equal(6, superseded.Publication.Events.Count, "Publication history should remain append-only.");
        VerificationAssert.Equal(6, superseded.Publication.ApprovalAuditTrail.Count, "Approval audit trail should stay append-only with lifecycle history.");
        VerificationAssert.Equal("retention-audit", superseded.Publication.ModerationTimeline.PendingDecision, "Superseded publications should project retention audit follow-up.");
        VerificationAssert.True(superseded.Publication.ModerationTimeline.NextSafeActionSummary?.Contains("install and audit history", StringComparison.OrdinalIgnoreCase) == true, "Superseded publications should expose an explicit retained-history next action summary.");

        var postPublishReview = workflow.Review(
            created.PublicationId,
            new PublicationReviewRequest("ops.reviewer", Approved: false, Notes: "too late"),
            superseded.Publication.ConcurrencyToken);
        VerificationAssert.Equal(PublicationMutationStatus.Conflict, postPublishReview.Status, "Immutable lifecycle publications should not re-enter review.");
    }
}
