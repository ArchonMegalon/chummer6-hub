using System.Globalization;
using System.Reflection;
using Chummer.Contracts.Receipts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignFederationReceiptEnvelopeTests
{
    [Fact]
    public void Source_pack_projection_emits_public_safe_route_receipt_envelope()
    {
        Type serviceType = typeof(CampaignFederationOrchestrationService);
        Type candidateType = serviceType.GetNestedType("FederationCandidate", BindingFlags.NonPublic)
            ?? throw new InvalidOperationException("FederationCandidate was not found.");
        MethodInfo method = serviceType.GetMethod("BuildSourcePackProjection", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildSourcePackProjection was not found.");

        object candidate = Activator.CreateInstance(
            candidateType,
            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
            binder: null,
            args:
            [
                "entry-1",
                "publication-1",
                "campaign-1",
                "Night Market Briefing",
                "Public-safe creator publication for the current campaign lane.",
                "creator_publication",
                "published",
                "artifact-1",
                "dossier-1",
                DateTimeOffset.Parse("2026-06-16T00:00:00Z", CultureInfo.InvariantCulture),
                false,
                false,
                false,
                new[] { "entry-1", "publication-1" },
                new[] { "keep public shelf current" }
            ],
            culture: null) ?? throw new InvalidOperationException("Could not construct FederationCandidate.");

        CampaignFederationSourcePackProjection projection =
            Assert.IsType<CampaignFederationSourcePackProjection>(method.Invoke(
                null,
                [candidate, new CampaignFederationBatchRequest()]));

        CampaignFederationRouteReceiptProjection routeReceipt = Assert.IsType<CampaignFederationRouteReceiptProjection>(projection.RouteReceipt);
        Assert.NotNull(routeReceipt.Envelope);
        Assert.Equal("campaign_federation_route", routeReceipt.Envelope!.ReceiptKind);
        Assert.Equal("community.campaign_federation", routeReceipt.Envelope.OwnerScope);
        Assert.Equal(ReceiptExposureClasses.PublicSafe, routeReceipt.Envelope.ExposureClass);
        Assert.Equal(ReceiptLifecycleStates.Published, routeReceipt.Envelope.LifecycleState);
        Assert.Equal(routeReceipt.ReceiptId, routeReceipt.Envelope.EvidenceRef);
    }

    [Fact]
    public void Campaign_spine_controller_rebuilds_route_payload_with_shared_envelope()
    {
        MethodInfo method = typeof(CampaignSpineController)
            .GetMethod("BuildRouteReceiptPayload", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildRouteReceiptPayload was not found.");

        CampaignFederationRouteReceiptProjection projection =
            Assert.IsType<CampaignFederationRouteReceiptProjection>(method.Invoke(
                null,
                [new LocalProofReceiptMatch(
                    ReceiptId: "public-shelf:/artifacts/publications/publication-1",
                    PackageId: "creator-publication:publication-1",
                    Summary: "Publication shelf route is live.",
                    MatchedRoute: "/artifacts/publications/publication-1",
                    MatchMode: "publication_status")]));

        Assert.NotNull(projection.Envelope);
        Assert.Equal("campaign_federation_route", projection.Envelope!.ReceiptKind);
        Assert.Equal("community.campaign_federation", projection.Envelope.OwnerScope);
        Assert.Equal(ReceiptExposureClasses.PublicSafe, projection.Envelope.ExposureClass);
        Assert.Equal(ReceiptLifecycleStates.Published, projection.Envelope.LifecycleState);
        Assert.Equal(projection.ReceiptId, projection.Envelope.EvidenceRef);
    }
}
