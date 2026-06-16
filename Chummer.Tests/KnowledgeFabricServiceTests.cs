using Chummer.Contracts.Receipts;
using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class KnowledgeFabricServiceTests
{
    [Fact]
    public void Knowledge_fabric_receipts_emit_shared_public_safe_envelopes()
    {
        KnowledgeFabricService service = new();

        IReadOnlyList<KnowledgeFabricReceipt> receipts = service.ListReceipts();

        Assert.NotEmpty(receipts);
        Assert.All(receipts, receipt =>
        {
            Assert.NotNull(receipt.Envelope);
            Assert.Equal("knowledge_fabric", receipt.Envelope!.ReceiptKind);
            Assert.Equal("rules.knowledge_fabric", receipt.Envelope.OwnerScope);
            Assert.Equal(ReceiptExposureClasses.PublicSafe, receipt.Envelope.ExposureClass);
            Assert.Equal(ReceiptLifecycleStates.Published, receipt.Envelope.LifecycleState);
            Assert.Equal("live", receipt.Envelope.ReviewState);
            Assert.Equal(receipt.ReceiptId, receipt.Envelope.EvidenceRef);
        });
    }
}
