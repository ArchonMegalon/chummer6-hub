using Chummer.Contracts.Receipts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class NexusPanContinuityServiceTests
{
    [Fact]
    public void Nexus_pan_receipts_emit_shared_public_safe_envelopes()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "nexus-pan-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(tempRoot, "install-linking-store.json")
                })
                .Build();
            InstallLinkingStore store = new(configuration, NullLogger<InstallLinkingStore>.Instance);
            NexusPanContinuityService service = new(store);

            IReadOnlyList<NexusPanReceipt> receipts = service.ListReceipts();

            Assert.NotEmpty(receipts);
            Assert.All(receipts, receipt =>
            {
                Assert.NotNull(receipt.Envelope);
                Assert.Equal("nexus_pan", receipt.Envelope!.ReceiptKind);
                Assert.Equal("play.nexus_pan", receipt.Envelope.OwnerScope);
                Assert.Equal(ReceiptExposureClasses.PublicSafe, receipt.Envelope.ExposureClass);
                Assert.Equal(ReceiptLifecycleStates.Published, receipt.Envelope.LifecycleState);
                Assert.Equal("live", receipt.Envelope.ReviewState);
                Assert.Equal(receipt.ReceiptId, receipt.Envelope.EvidenceRef);
            });
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }
}
