using Chummer.Contracts.Receipts;
using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicPackageCatalogServiceTests
{
    [Fact]
    public void Public_package_receipts_emit_shared_public_safe_envelopes()
    {
        PublicPackageCatalogService service = new();

        PublicPackageReceipt vote = service.RecordVote("desktop-preview", "subject-1", "Runner One");
        PublicPackageReceipt follow = service.RecordFollow("desktop-preview", "subject-2", "Runner Two");
        PublicPackageReceipt revoke = service.RecordRevoke("desktop-preview", "follow", "subject-2", "Runner Two");

        Assert.Equal("vote", vote.Envelope!.ReviewState);
        Assert.Equal("follow", follow.Envelope!.ReviewState);
        Assert.Equal("revoke_follow", revoke.Envelope!.ReviewState);

        Assert.All(new[] { vote, follow, revoke }, receipt =>
        {
            Assert.NotNull(receipt.Envelope);
            Assert.Equal("public_package", receipt.Envelope!.ReceiptKind);
            Assert.Equal("public.package_catalog", receipt.Envelope.OwnerScope);
            Assert.Equal(ReceiptExposureClasses.PublicSafe, receipt.Envelope.ExposureClass);
            Assert.Equal(receipt.ReceiptId, receipt.Envelope.EvidenceRef);
        });
    }
}
