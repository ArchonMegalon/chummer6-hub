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
        Assert.Equal("/docs/chummer6-quickstart/download.pdf", document.PdfArtifactPath);
        Assert.False(string.IsNullOrWhiteSpace(document.PdfSha256));
        Assert.Equal(64, document.PdfSha256.Length);
        Assert.Equal(ChummerDocumentStatuses.Published, document.Status);
        Assert.NotNull(document.PublishedAtUtc);
        Assert.Equal(ChummerDocumentClassifications.Public, document.PublicClassification);
    }

    [Fact]
    public void QuickstartPublicationSeparatesRouteReadinessFromExternalViewerPublication()
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
        Assert.Equal(ChummerDocumentStatuses.Published, document.Status);
        Assert.False(publication.AnalyticsEnabled);
        Assert.False(publication.LeadCaptureEnabled);
        Assert.False(publication.PaywallEnabled);
        Assert.Equal(document.PdfSha256, receipt!.PdfSha256);
        Assert.Equal("pass_first_party_doc_boundary", receipt.PrivacyScanStatus);
        Assert.Equal("pass_first_party_doc_boundary", receipt.CopyrightScanStatus);
        Assert.Equal("/docs/embed/chummer6-quickstart", receipt.EmbedRoute);
    }

    [Fact]
    public void QuickstartPdfFallbackArtifactIsAvailableAndStable()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new FlipLinkDocumentPortalService(configuration);

        var artifact = service.TryBuildPdfArtifact("chummer6-quickstart");

        Assert.NotNull(artifact);
        Assert.Equal("application/pdf", artifact!.ContentType);
        Assert.Equal("chummer6-quickstart-guide.pdf", artifact.FileName);
        Assert.StartsWith("%PDF-1.4", System.Text.Encoding.ASCII.GetString(artifact.Bytes.Take(8).ToArray()));
        Assert.Equal(64, artifact.Sha256.Length);
    }
}
