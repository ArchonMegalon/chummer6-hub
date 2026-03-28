using System.Text.Json;
using Chummer.Run.Api.ViewModels;

namespace Chummer.Run.Api.Services;

public sealed class PublicPrivacyBoundaryService
{
    private const string PrivacyBoundariesRelativePath = ".codex-design/product/PUBLIC_PRIVACY_BOUNDARIES.yaml";
    private const string DefaultContractName = "chummer.public_privacy_boundaries";
    private const string SourceDocument = "products/chummer/PUBLIC_PRIVACY_BOUNDARIES.yaml";
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    private readonly PublicCanonFileLoader _canon;
    private readonly PublicRouteCatalogService _routes;

    public PublicPrivacyBoundaryService(PublicCanonFileLoader canon, PublicRouteCatalogService routes)
    {
        _canon = canon;
        _routes = routes;
    }

    public PrivacyBoundaryPanelViewModel BuildPanel(string pageId)
    {
        var document = LoadDocument();
        var (primaryAction, secondaryAction) = BuildActions(pageId);

        return new PrivacyBoundaryPanelViewModel(
            Eyebrow: RequireText(document.Eyebrow, "privacy boundary eyebrow"),
            Heading: RequireText(document.Heading, "privacy boundary heading"),
            Summary: RequireText(document.Summary, "privacy boundary summary"),
            MicroProof: document.MicroProof?.ToArray() ?? Array.Empty<string>(),
            Domains: (document.Domains ?? new List<PublicPrivacyBoundaryDomainDocument>())
                .Select(domain => new PrivacyBoundaryDomainViewModel(
                    Label: RequireText(domain.Label, "privacy boundary domain label"),
                    Owner: RequireText(domain.Owner, $"privacy boundary domain '{domain.Id}' owner"),
                    RetentionSummary: RequireText(domain.RetentionSummary, $"privacy boundary domain '{domain.Id}' retention summary"),
                    RedactionSummary: RequireText(domain.RedactionSummary, $"privacy boundary domain '{domain.Id}' redaction summary"),
                    PublicProjection: RequireText(domain.PublicProjection, $"privacy boundary domain '{domain.Id}' public projection"),
                    SignedInProjection: RequireText(domain.SignedInProjection, $"privacy boundary domain '{domain.Id}' signed-in projection")))
                .ToArray(),
            SurfaceRules: (document.SurfaceRules ?? new List<PublicPrivacyBoundarySurfaceRuleDocument>())
                .Select(rule => new PrivacyBoundarySurfaceRuleViewModel(
                    Label: RequireText(rule.Label, $"privacy boundary surface rule '{rule.Id}' label"),
                    Summary: RequireText(rule.Summary, $"privacy boundary surface rule '{rule.Id}' summary"),
                    BlockedSummary: RequireText(rule.BlockedSummary, $"privacy boundary surface rule '{rule.Id}' blocked summary")))
                .ToArray(),
            PrimaryAction: primaryAction,
            SecondaryAction: secondaryAction);
    }

    public string LoadArtifactJson()
    {
        var document = LoadDocument();
        var artifact = new PublicPrivacyBoundaryArtifact(
            ContractName: string.IsNullOrWhiteSpace(document.ContractName) ? DefaultContractName : document.ContractName!,
            ContractVersion: document.Version,
            AsOf: document.AsOf ?? string.Empty,
            SourceDocument: SourceDocument,
            Eyebrow: RequireText(document.Eyebrow, "privacy boundary eyebrow"),
            Heading: RequireText(document.Heading, "privacy boundary heading"),
            Summary: RequireText(document.Summary, "privacy boundary summary"),
            MicroProof: document.MicroProof?.ToArray() ?? Array.Empty<string>(),
            Domains: (document.Domains ?? new List<PublicPrivacyBoundaryDomainDocument>())
                .Select(domain => new PublicPrivacyBoundaryArtifactDomain(
                    Id: RequireText(domain.Id, "privacy boundary domain id"),
                    Label: RequireText(domain.Label, $"privacy boundary domain '{domain.Id}' label"),
                    Owner: RequireText(domain.Owner, $"privacy boundary domain '{domain.Id}' owner"),
                    RetentionSummary: RequireText(domain.RetentionSummary, $"privacy boundary domain '{domain.Id}' retention summary"),
                    RedactionSummary: RequireText(domain.RedactionSummary, $"privacy boundary domain '{domain.Id}' redaction summary"),
                    PublicProjection: RequireText(domain.PublicProjection, $"privacy boundary domain '{domain.Id}' public projection"),
                    SignedInProjection: RequireText(domain.SignedInProjection, $"privacy boundary domain '{domain.Id}' signed-in projection")))
                .ToArray(),
            SurfaceRules: (document.SurfaceRules ?? new List<PublicPrivacyBoundarySurfaceRuleDocument>())
                .Select(rule => new PublicPrivacyBoundaryArtifactSurfaceRule(
                    Id: RequireText(rule.Id, "privacy boundary surface rule id"),
                    Label: RequireText(rule.Label, $"privacy boundary surface rule '{rule.Id}' label"),
                    Summary: RequireText(rule.Summary, $"privacy boundary surface rule '{rule.Id}' summary"),
                    BlockedSummary: RequireText(rule.BlockedSummary, $"privacy boundary surface rule '{rule.Id}' blocked summary")))
                .ToArray());

        return JsonSerializer.Serialize(artifact, JsonOptions);
    }

    private (TrustPageActionViewModel PrimaryAction, TrustPageActionViewModel SecondaryAction) BuildActions(string pageId)
    {
        var primary = pageId switch
        {
            "help" or "contact" => new TrustPageActionViewModel("Read privacy", "/privacy", "secondary"),
            _ => new TrustPageActionViewModel("Open help", "/help", "secondary")
        };
        var secondary = pageId switch
        {
            "contact" => new TrustPageActionViewModel("Open help", "/help", "ghost"),
            _ => new TrustPageActionViewModel("Open support intake", "/contact#support-intake", "ghost")
        };

        _routes.ValidateRouteTarget(primary.Href, $"privacy boundary action '{primary.Label}'");
        _routes.ValidateRouteTarget(secondary.Href, $"privacy boundary action '{secondary.Label}'");
        return (primary, secondary);
    }

    private PublicPrivacyBoundariesDocument LoadDocument()
        => _canon.LoadRequiredYaml<PublicPrivacyBoundariesDocument>(PrivacyBoundariesRelativePath);

    private static string RequireText(string? value, string description)
        => string.IsNullOrWhiteSpace(value)
            ? throw new InvalidOperationException($"{description} is missing required text.")
            : value;

    private sealed record PublicPrivacyBoundaryArtifact(
        string ContractName,
        int ContractVersion,
        string AsOf,
        string SourceDocument,
        string Eyebrow,
        string Heading,
        string Summary,
        IReadOnlyList<string> MicroProof,
        IReadOnlyList<PublicPrivacyBoundaryArtifactDomain> Domains,
        IReadOnlyList<PublicPrivacyBoundaryArtifactSurfaceRule> SurfaceRules);

    private sealed record PublicPrivacyBoundaryArtifactDomain(
        string Id,
        string Label,
        string Owner,
        string RetentionSummary,
        string RedactionSummary,
        string PublicProjection,
        string SignedInProjection);

    private sealed record PublicPrivacyBoundaryArtifactSurfaceRule(
        string Id,
        string Label,
        string Summary,
        string BlockedSummary);
}
