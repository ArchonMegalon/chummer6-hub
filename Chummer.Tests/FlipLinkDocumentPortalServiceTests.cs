using Chummer.Contracts.Content;
using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class FlipLinkDocumentPortalServiceTests
{
    [Fact]
    public void QuickstartDocumentUsesRealSourceGuideAndHasStableSourceHash()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new FlipLinkDocumentPortalService(configuration);

        ChummerDocument? document = service.TryGetPublicDocument("chummer6-quickstart");

        Assert.NotNull(document);
        Assert.Equal("chummer6_quickstart_guide", document!.Id);
        Assert.Equal("quickstart", document.Category);
        Assert.Equal("products/chummer/public-guides/chummer6-quickstart.md", document.SourcePath);
        Assert.Equal("chummer6-design", document.SourceRepo);
        Assert.False(string.IsNullOrWhiteSpace(document.SourceHash));
        Assert.Equal(64, document.SourceHash.Length);
        Assert.Equal(ChummerDocumentStatuses.Approved, document.Status);
        Assert.Equal(ChummerDocumentClassifications.Public, document.PublicClassification);
    }

    [Fact]
    public void QuickstartPublicationReceiptStaysCandidateOnlyUntilProviderProofExists()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new FlipLinkDocumentPortalService(configuration);

        var document = service.TryGetPublicDocument("chummer6-quickstart");
        var publication = service.TryGetPublication(document!.Id);
        var receipt = service.TryBuildPublicationReceipt("chummer6-quickstart");

        Assert.NotNull(publication);
        Assert.NotNull(receipt);
        Assert.Equal("FlipLink.me", publication!.Provider);
        Assert.Equal(FlipLinkPublicationStatuses.Unpublished, publication.PublicationStatus);
        Assert.False(publication.AnalyticsEnabled);
        Assert.False(publication.LeadCaptureEnabled);
        Assert.False(publication.PaywallEnabled);
        Assert.Equal("pending_manual_scan", receipt!.PrivacyScanStatus);
        Assert.Equal("pending_manual_scan", receipt.CopyrightScanStatus);
        Assert.Equal("/docs/embed/chummer6-quickstart", receipt.EmbedRoute);
    }
}
