using System.Security.Cryptography;
using System.Text;
using Chummer.Contracts.Content;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services;

public sealed class FlipLinkDocumentPortalService
{
    private static readonly DocumentDefinition Quickstart = new(
        Id: "chummer6_quickstart_guide",
        Slug: "chummer6-quickstart",
        Category: "quickstart",
        RelativeGuidePath: "public-guides/chummer6-quickstart.md",
        SourceRepo: "chummer6-design",
        SourcePath: "products/chummer/public-guides/chummer6-quickstart.md",
        Version: "2026.06-first-lane",
        PdfFileName: "chummer6-quickstart-guide.pdf",
        Title: "Chummer6 Quickstart Guide",
        Audience: "new_players_and_operators",
        CreatedAtUtc: new DateTimeOffset(2026, 6, 6, 0, 0, 0, TimeSpan.Zero));

    private static readonly DocumentDefinition OriginDossier = new(
        Id: "origin_dossier_name_she_chose",
        Slug: "origin-dossier-the-name-she-chose",
        Category: "origin-dossier",
        RelativeGuidePath: "horizons/origin-dossier.md",
        SourceRepo: "chummer6-design",
        SourcePath: "products/chummer/horizons/origin-dossier.md",
        Version: "2026.06-story-first-lane",
        PdfFileName: "origin-dossier-the-name-she-chose.pdf",
        Title: "Origin Dossier: The Name She Chose",
        Audience: "players_and_gms",
        CreatedAtUtc: new DateTimeOffset(2026, 6, 19, 0, 0, 0, TimeSpan.Zero));

    private static readonly IReadOnlyList<DocumentDefinition> PublicDocuments =
    [
        Quickstart,
        OriginDossier
    ];

    private readonly string _productRoot;

    public FlipLinkDocumentPortalService(IConfiguration configuration)
    {
        _productRoot = ResolveProductRoot(configuration);
    }

    public IReadOnlyList<ChummerDocument> ListPublicDocuments()
        => PublicDocuments.Select(BuildDocument).ToArray();

    public IReadOnlyList<ChummerDocument> ListCategoryDocuments(string category)
        => PublicDocuments
            .Where(item => string.Equals(item.Category, category?.Trim(), StringComparison.OrdinalIgnoreCase))
            .Select(BuildDocument)
            .ToArray();

    public ChummerDocument? TryGetPublicDocument(string slug)
        => TryFindDefinitionBySlug(slug) is { } definition ? BuildDocument(definition) : null;

    public FlipLinkPublication? TryGetPublication(string documentId)
    {
        DocumentDefinition? definition = TryFindDefinitionById(documentId);
        if (definition is null)
        {
            return null;
        }

        return new FlipLinkPublication(
            Id: $"fliplink_{definition.Id}_candidate",
            ChummerDocumentId: definition.Id,
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
            CreatedAtUtc: definition.CreatedAtUtc);
    }

    public FlipLinkPublicationReceipt? TryBuildPublicationReceipt(string slug)
    {
        ChummerDocument? document = TryGetPublicDocument(slug);
        if (document is null)
        {
            return null;
        }

        FlipLinkPublication? publication = TryGetPublication(document.Id);
        if (publication is null)
        {
            return null;
        }

        return new FlipLinkPublicationReceipt(
            Id: $"fliplink_{document.Id}_publication_receipt",
            PublicationId: publication.Id,
            DocumentId: document.Id,
            PdfSha256: document.PdfSha256,
            PrivacyScanStatus: "pass_first_party_doc_boundary",
            CopyrightScanStatus: "pass_first_party_doc_boundary",
            AccessPolicy: document.AccessPolicy,
            ProviderUrl: publication.FlipLinkUrl,
            EmbedRoute: $"/docs/embed/{document.Slug}",
            CreatedAtUtc: document.CreatedAtUtc);
    }

    public DocumentPortalPdfArtifact? TryBuildPdfArtifact(string slug)
    {
        DocumentDefinition? definition = TryFindDefinitionBySlug(slug);
        if (definition is null)
        {
            return null;
        }

        string sourceFullPath = Path.Combine(_productRoot, definition.RelativeGuidePath);
        if (!File.Exists(sourceFullPath))
        {
            return null;
        }

        IReadOnlyList<string> lines = BuildPdfLines(definition.Title, File.ReadAllText(sourceFullPath));
        byte[] bytes = MinimalPdfDocumentRenderer.Render(lines);
        return new DocumentPortalPdfArtifact(
            FileName: definition.PdfFileName,
            Bytes: bytes,
            Sha256: ComputeSha256(bytes),
            ContentType: "application/pdf");
    }

    private ChummerDocument BuildDocument(DocumentDefinition definition)
    {
        string sourceFullPath = Path.Combine(_productRoot, definition.RelativeGuidePath);
        string sourceHash = ComputeFileSha256(sourceFullPath);
        DocumentPortalPdfArtifact? pdfArtifact = TryBuildPdfArtifact(definition.Slug);

        return new ChummerDocument(
            Id: definition.Id,
            Slug: definition.Slug,
            Title: definition.Title,
            Category: definition.Category,
            SourceRepo: definition.SourceRepo,
            SourcePath: definition.SourcePath,
            SourceHash: sourceHash,
            PdfArtifactPath: $"/docs/{definition.Slug}/download.pdf",
            PdfSha256: pdfArtifact?.Sha256 ?? string.Empty,
            PublicClassification: ChummerDocumentClassifications.Public,
            Audience: definition.Audience,
            AccessPolicy: "public",
            FlipLinkPublicationId: $"fliplink_{definition.Id}_candidate",
            FlipLinkUrl: string.Empty,
            FlipLinkEmbedCodeHash: string.Empty,
            AnalyticsEnabled: false,
            LeadCaptureEnabled: false,
            PasswordProtected: false,
            Version: definition.Version,
            Status: ChummerDocumentStatuses.Published,
            CreatedAtUtc: definition.CreatedAtUtc,
            PublishedAtUtc: definition.CreatedAtUtc);
    }

    private static string ResolveProductRoot(IConfiguration configuration)
    {
        string? configuredRoot = configuration["CHUMMER_PUBLIC_CANON_ROOT"];
        if (!string.IsNullOrWhiteSpace(configuredRoot))
        {
            string absoluteRoot = Path.GetFullPath(configuredRoot);
            string rootedProductPath = Path.Combine(absoluteRoot, "products", "chummer");
            if (File.Exists(Path.Combine(rootedProductPath, Quickstart.RelativeGuidePath)))
            {
                return rootedProductPath;
            }

            string siblingProductPath = Path.GetFullPath(Path.Combine(absoluteRoot, "..", "chummer-design", "products", "chummer"));
            if (File.Exists(Path.Combine(siblingProductPath, Quickstart.RelativeGuidePath)))
            {
                return siblingProductPath;
            }

            string mirroredProductPath = Path.Combine(absoluteRoot, ".codex-design", "product");
            if (File.Exists(Path.Combine(mirroredProductPath, Quickstart.RelativeGuidePath)))
            {
                return mirroredProductPath;
            }
        }

        foreach (string candidate in ResolveAncestorProductRoots(Directory.GetCurrentDirectory()))
        {
            if (TryResolveProductRoot(candidate, out string matchedRoot))
            {
                return matchedRoot;
            }
        }

        foreach (string candidate in ResolveAncestorProductRoots(AppContext.BaseDirectory))
        {
            if (TryResolveProductRoot(candidate, out string matchedRoot))
            {
                return matchedRoot;
            }
        }

        return Path.Combine(AppContext.BaseDirectory, ".codex-design", "product");
    }

    private static bool TryResolveProductRoot(string rootCandidate, out string productRoot)
    {
        foreach (string candidate in BuildProductRootCandidates(rootCandidate))
        {
            if (File.Exists(Path.Combine(candidate, Quickstart.RelativeGuidePath)))
            {
                productRoot = candidate;
                return true;
            }
        }

        productRoot = string.Empty;
        return false;
    }

    private static IEnumerable<string> BuildProductRootCandidates(string root)
    {
        string fullRoot = Path.GetFullPath(root);
        yield return fullRoot;
        yield return Path.Combine(fullRoot, "products", "chummer");
        yield return Path.Combine(fullRoot, "chummer-design", "products", "chummer");
        yield return Path.Combine(fullRoot, ".codex-design", "product");
    }

    private static IEnumerable<string> ResolveAncestorProductRoots(string start)
    {
        string? current = Path.GetFullPath(start);
        for (int depth = 0; depth < 8 && !string.IsNullOrWhiteSpace(current); depth++)
        {
            yield return current;
            current = Directory.GetParent(current)?.FullName;
        }
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

    private static string ComputeSha256(byte[] bytes)
    {
        byte[] digest = SHA256.HashData(bytes);
        StringBuilder builder = new(digest.Length * 2);
        foreach (byte value in digest)
        {
            builder.Append(value.ToString("x2"));
        }

        return builder.ToString();
    }

    private static DocumentDefinition? TryFindDefinitionBySlug(string? slug)
        => PublicDocuments.FirstOrDefault(item => string.Equals(item.Slug, slug?.Trim(), StringComparison.OrdinalIgnoreCase));

    private static DocumentDefinition? TryFindDefinitionById(string? documentId)
        => PublicDocuments.FirstOrDefault(item => string.Equals(item.Id, documentId?.Trim(), StringComparison.OrdinalIgnoreCase));

    private static IReadOnlyList<string> BuildPdfLines(string title, string markdown)
    {
        List<string> lines =
        [
            title,
            string.Empty,
            "Created and owned by Chummer.",
            "FlipLink can be an optional viewer; the Chummer page remains the source.",
            string.Empty
        ];

        foreach (string rawLine in markdown.Split('\n'))
        {
            string normalized = NormalizeMarkdownLine(rawLine);
            if (string.IsNullOrWhiteSpace(normalized))
            {
                lines.Add(string.Empty);
                continue;
            }

            foreach (string wrapped in WrapLine(normalized, 92))
            {
                lines.Add(wrapped);
            }
        }

        return lines;
    }

    private static string NormalizeMarkdownLine(string line)
    {
        string normalized = line.Replace("\r", string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return string.Empty;
        }

        while (normalized.StartsWith("#", StringComparison.Ordinal))
        {
            normalized = normalized[1..].TrimStart();
        }

        if (normalized.StartsWith("- ", StringComparison.Ordinal) || normalized.StartsWith("* ", StringComparison.Ordinal))
        {
            normalized = "• " + normalized[2..].TrimStart();
        }

        normalized = normalized.Replace("`", string.Empty).Replace("**", string.Empty);
        return normalized.Trim();
    }

    private static IReadOnlyList<string> WrapLine(string line, int width)
    {
        if (line.Length <= width)
        {
            return [line];
        }

        List<string> wrapped = [];
        string remaining = line;
        while (remaining.Length > width)
        {
            int split = remaining.LastIndexOf(' ', width);
            if (split <= 0)
            {
                split = width;
            }

            wrapped.Add(remaining[..split].Trim());
            remaining = remaining[split..].TrimStart();
        }

        if (!string.IsNullOrWhiteSpace(remaining))
        {
            wrapped.Add(remaining);
        }

        return wrapped;
    }

    public sealed record DocumentPortalPdfArtifact(
        string FileName,
        byte[] Bytes,
        string Sha256,
        string ContentType);

    private sealed record DocumentDefinition(
        string Id,
        string Slug,
        string Category,
        string RelativeGuidePath,
        string SourceRepo,
        string SourcePath,
        string Version,
        string PdfFileName,
        string Title,
        string Audience,
        DateTimeOffset CreatedAtUtc);

    private static class MinimalPdfDocumentRenderer
    {
        public static byte[] Render(IReadOnlyList<string> lines)
        {
            const int linesPerPage = 46;
            List<string> pages = [];
            for (int index = 0; index < lines.Count; index += linesPerPage)
            {
                pages.Add(RenderPage(lines.Skip(index).Take(linesPerPage)));
            }

            List<byte[]> objects = [];
            objects.Add(Encoding.ASCII.GetBytes("<< /Type /Catalog /Pages 2 0 R >>"));
            objects.Add(Encoding.ASCII.GetBytes($"<< /Type /Pages /Count {pages.Count} /Kids [{string.Join(" ", Enumerable.Range(0, pages.Count).Select(page => $"{3 + page} 0 R"))}] >>"));
            foreach (string _ in pages)
            {
                objects.Add(Array.Empty<byte>());
            }

            objects.Add(Encoding.ASCII.GetBytes("<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"));

            for (int pageIndex = 0; pageIndex < pages.Count; pageIndex++)
            {
                int pageObjectNumber = 3 + pageIndex;
                int contentObjectNumber = 3 + pages.Count + pageIndex + 1;
                objects[pageObjectNumber - 1] = Encoding.ASCII.GetBytes(
                    $"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {3 + pages.Count} 0 R >> >> /Contents {contentObjectNumber} 0 R >>");
            }

            foreach (string page in pages)
            {
                byte[] pageStream = Encoding.ASCII.GetBytes(page);
                byte[] header = Encoding.ASCII.GetBytes($"<< /Length {pageStream.Length} >>\nstream\n");
                byte[] footer = Encoding.ASCII.GetBytes("\nendstream");
                byte[] content = new byte[header.Length + pageStream.Length + footer.Length];
                Buffer.BlockCopy(header, 0, content, 0, header.Length);
                Buffer.BlockCopy(pageStream, 0, content, header.Length, pageStream.Length);
                Buffer.BlockCopy(footer, 0, content, header.Length + pageStream.Length, footer.Length);
                objects.Add(content);
            }

            using MemoryStream stream = new();
            using StreamWriter writer = new(stream, Encoding.ASCII, 1024, leaveOpen: true);
            writer.Write("%PDF-1.4\n");
            writer.Flush();

            List<long> offsets = [0];
            for (int index = 0; index < objects.Count; index++)
            {
                offsets.Add(stream.Position);
                writer.Write($"{index + 1} 0 obj\n");
                writer.Flush();
                stream.Write(objects[index], 0, objects[index].Length);
                writer.Write("\nendobj\n");
                writer.Flush();
            }

            long xrefOffset = stream.Position;
            writer.Write($"xref\n0 {objects.Count + 1}\n");
            writer.Write("0000000000 65535 f \n");
            foreach (long offset in offsets.Skip(1))
            {
                writer.Write($"{offset:D10} 00000 n \n");
            }

            writer.Write($"trailer\n<< /Size {objects.Count + 1} /Root 1 0 R >>\nstartxref\n{xrefOffset}\n%%EOF");
            writer.Flush();
            return stream.ToArray();
        }

        private static string RenderPage(IEnumerable<string> lines)
        {
            StringBuilder builder = new();
            builder.Append("BT\n/F1 11 Tf\n14 TL\n72 748 Td\n");
            bool firstLine = true;
            foreach (string line in lines)
            {
                string escaped = EscapePdfText(line);
                if (!firstLine)
                {
                    builder.Append("T*\n");
                }

                builder.Append('(').Append(escaped).Append(") Tj\n");
                firstLine = false;
            }

            builder.Append("ET");
            return builder.ToString();
        }

        private static string EscapePdfText(string value)
            => value
                .Replace("\\", "\\\\", StringComparison.Ordinal)
                .Replace("(", "\\(", StringComparison.Ordinal)
                .Replace(")", "\\)", StringComparison.Ordinal);
    }
}
