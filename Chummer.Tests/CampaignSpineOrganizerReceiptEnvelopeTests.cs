using System.Reflection;
using Chummer.Campaign.Contracts;
using Chummer.Contracts.Receipts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Community;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignSpineOrganizerReceiptEnvelopeTests
{
    [Fact]
    public void Organizer_artifact_publication_receipts_emit_shared_envelopes()
    {
        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("BuildOrganizerArtifactPublicationReceipts", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildOrganizerArtifactPublicationReceipts was not found.");

        CampaignWorkspaceProjection workspace = new(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-1",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: new RuleEnvironmentRef("env-1", "campaign", "sr5-core", "approved", [], [], []),
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf:
            [
                new PublicationSafeProjection(
                    ProjectionId: "recap-1",
                    Kind: "creator_publication",
                    Label: "Night Market Recap",
                    Summary: "Player-safe recap remains discoverable on the governed publication rail.",
                    Audience: "public",
                    PublicationState: "published",
                    TrustBand: "public_safe",
                    Discoverable: true,
                    PublicationSummary: "Published on the governed public shelf.",
                    CreatorPublicationId: "publication-1",
                    NextSafeAction: "Keep the same publication receipt attached.",
                    AuditSummary: "Published after moderation review.")
            ],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return to the campaign workspace.");

        IReadOnlyList<OrganizerArtifactPublicationReceiptProjection> receipts =
            Assert.IsAssignableFrom<IReadOnlyList<OrganizerArtifactPublicationReceiptProjection>>(method.Invoke(
                null,
                new object?[] { new[] { workspace } }));

        OrganizerArtifactPublicationReceiptProjection receipt = Assert.Single(receipts);
        Assert.NotNull(receipt.Envelope);
        Assert.Equal("organizer_artifact_publication", receipt.Envelope!.ReceiptKind);
        Assert.Equal("community.organizer_ops", receipt.Envelope.OwnerScope);
        Assert.Equal(ReceiptExposureClasses.PublicSafe, receipt.Envelope.ExposureClass);
        Assert.Equal(ReceiptLifecycleStates.Published, receipt.Envelope.LifecycleState);
        Assert.Equal("publication-1", receipt.Envelope.EvidenceRef);
    }
}
