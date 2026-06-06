using System.Security.Cryptography;
using System.Text;
using Chummer.Contracts.Content;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services;

public sealed class FlipLinkDocumentPortalService
{
    private const string QuickstartDocumentId = "chummer6_quickstart_guide";
    private const string QuickstartSlug = "chummer6-quickstart";
    private const string QuickstartCategory = "quickstart";
    private const string QuickstartSourceRepo = "chummer6-design";
    private const string QuickstartSourcePath = "products/chummer/public-guides/chummer6-quickstart.md";
    private const string QuickstartVersion = "2026.06-first-lane";
    private static readonly DateTimeOffset QuickstartCreatedAtUtc = new(2026, 6, 6, 0, 0, 0, TimeSpan.Zero);

    private readonly string _productRoot;

    public FlipLinkDocumentPortalService(IConfiguration configuration)
    {
        _productRoot = ResolveProductRoot(configuration);
    }

    public IReadOnlyList<ChummerDocument> ListPublicDocuments()
        => [BuildQuickstartDocument()];

    public IReadOnlyList<ChummerDocument> ListCategoryDocuments(string category)
        => string.Equals(category?.Trim(), QuickstartCategory, StringComparison.OrdinalIgnoreCase)
            ? [BuildQuickstartDocument()]
            : [];

    public ChummerDocument? TryGetPublicDocument(string slug)
        => string.Equals(slug?.Trim(), QuickstartSlug, StringComparison.OrdinalIgnoreCase)
            ? BuildQuickstartDocument()
            : null;

    public FlipLinkPublication? TryGetPublication(string documentId)
    {
        if (!string.Equals(documentId?.Trim(), QuickstartDocumentId, StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        return new FlipLinkPublication(
            Id: "fliplink_chummer6_quickstart_candidate",
            ChummerDocumentId: QuickstartDocumentId,
            Provider: "FlipLink.me",
            ProviderPublicationId: string.Empty,
            FlipLinkUrl: string.Empty,
            EmbedCodeHash: string.Empty,
            CnameUrl: string.Empty,
            PasswordProtected: false,
            LeadCaptureEnabled: false,
            PaywallEnabled: false,
            AnalyticsEnabled: false,
            PublicationStatus: FlipLinkPublicationStatuses.Unpublished,
            CreatedByUserId: "operator_managed_publication_lane",
            CreatedAtUtc: QuickstartCreatedAtUtc);
    }

    public FlipLinkPublicationReceipt? TryBuildPublicationReceipt(string slug)
    {
        var document = TryGetPublicDocument(slug);
        if (document is null)
        {
            return null;
        }

        var publication = TryGetPublication(document.Id);
        if (publication is null)
        {
            return null;
        }

        return new FlipLinkPublicationReceipt(
            Id: "fliplink_chummer6_quickstart_publication_receipt",
            PublicationId: publication.Id,
            DocumentId: document.Id,
            PdfSha256: document.PdfSha256,
            PrivacyScanStatus: "pending_manual_scan",
            CopyrightScanStatus: "pending_manual_scan",
            AccessPolicy: document.AccessPolicy,
            ProviderUrl: publication.FlipLinkUrl,
            EmbedRoute: $"/docs/embed/{document.Slug}",
            CreatedAtUtc: QuickstartCreatedAtUtc);
    }

    private ChummerDocument BuildQuickstartDocument()
    {
        string sourceFullPath = Path.Combine(_productRoot, "public-guides", "chummer6-quickstart.md");
        string sourceHash = ComputeFileSha256(sourceFullPath);

        return new ChummerDocument(
            Id: QuickstartDocumentId,
            Slug: QuickstartSlug,
            Title: "Chummer6 Quickstart Guide",
            Category: QuickstartCategory,
            SourceRepo: QuickstartSourceRepo,
            SourcePath: QuickstartSourcePath,
            SourceHash: sourceHash,
            PdfArtifactPath: string.Empty,
            PdfSha256: string.Empty,
            PublicClassification: ChummerDocumentClassifications.Public,
            Audience: "new_players_and_operators",
            AccessPolicy: "public",
            FlipLinkPublicationId: "fliplink_chummer6_quickstart_candidate",
            FlipLinkUrl: string.Empty,
            FlipLinkEmbedCodeHash: string.Empty,
            AnalyticsEnabled: false,
            LeadCaptureEnabled: false,
            PasswordProtected: false,
            Version: QuickstartVersion,
            Status: ChummerDocumentStatuses.Approved,
            CreatedAtUtc: QuickstartCreatedAtUtc,
            PublishedAtUtc: null);
    }

    private static string ResolveProductRoot(IConfiguration configuration)
    {
        string? configuredRoot = configuration["CHUMMER_PUBLIC_CANON_ROOT"];
        if (!string.IsNullOrWhiteSpace(configuredRoot))
        {
            string absoluteRoot = Path.GetFullPath(configuredRoot);
            string rootedProductPath = Path.Combine(absoluteRoot, "products", "chummer");
            if (File.Exists(Path.Combine(rootedProductPath, "public-guides", "chummer6-quickstart.md")))
            {
                return rootedProductPath;
            }

            string siblingProductPath = Path.GetFullPath(Path.Combine(absoluteRoot, "..", "chummer-design", "products", "chummer"));
            if (File.Exists(Path.Combine(siblingProductPath, "public-guides", "chummer6-quickstart.md")))
            {
                return siblingProductPath;
            }

            string mirroredProductPath = Path.Combine(absoluteRoot, ".codex-design", "product");
            if (File.Exists(Path.Combine(mirroredProductPath, "public-guides", "chummer6-quickstart.md")))
            {
                return mirroredProductPath;
            }
        }

        return Path.Combine(AppContext.BaseDirectory, ".codex-design", "product");
    }

    private static string ComputeFileSha256(string path)
    {
        if (!File.Exists(path))
        {
            return string.Empty;
        }

        byte[] bytes = File.ReadAllBytes(path);
        byte[] digest = SHA256.HashData(bytes);
        StringBuilder builder = new(digest.Length * 2);
        foreach (byte value in digest)
        {
            builder.Append(value.ToString("x2"));
        }

        return builder.ToString();
    }
}
