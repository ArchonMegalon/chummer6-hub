using Chummer.Contracts.Receipts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Ledger;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class LedgerServiceTests
{
    [Fact]
    public void Ingest_canonicalizes_contribution_receipts_with_runtime_envelope_defaults()
    {
        CommunityStore store = CreateStore();
        LedgerService service = new(store, new RewardService(store), new EntitlementService(store));

        ReceiptIngestResultDto result = service.Ingest(new ContributionReceiptDto(
            ReceiptId: " rcpt-1 ",
            EventKind: " slice_landed ",
            LaneId: " lane-a ",
            ProjectId: " proj-a ",
            UserId: " user-a ",
            GroupId: " group-a ",
            SponsorSessionId: null,
            ParticipantCodexCode: null,
            AuthClass: " operator ",
            LaneType: " direct ",
            Verified: true));

        Assert.Equal("ingested", result.Status);
        ContributionReceiptDto receipt = Assert.Single(store.Receipts);
        Assert.NotNull(receipt.Envelope);
        Assert.Equal(ReceiptProvenanceClasses.Runtime, receipt.Envelope!.ProvenanceClass);
        Assert.Equal(ReceiptExposureClasses.SignedIn, receipt.Envelope.ExposureClass);
        Assert.Equal(ReceiptLifecycleStates.Verified, receipt.Envelope.LifecycleState);
        Assert.Equal("community.group", receipt.Envelope.OwnerScope);
        Assert.Equal("community_contribution", receipt.Envelope.ReceiptKind);
        Assert.Equal("verified", receipt.Envelope.ReviewState);
        Assert.Equal("rcpt-1", receipt.Envelope.EvidenceRef);
        Assert.Equal("rcpt-1", receipt.ReceiptId);
        Assert.Equal("slice_landed", receipt.EventKind);
        Assert.Equal("lane-a", receipt.LaneId);
        Assert.Equal("proj-a", receipt.ProjectId);
        Assert.Equal("user-a", receipt.UserId);
        Assert.Equal("group-a", receipt.GroupId);
    }

    private static CommunityStore CreateStore()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-ledger-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(root, "community.json")
            })
            .Build();
        return new CommunityStore(configuration, NullLogger<CommunityStore>.Instance);
    }
}
