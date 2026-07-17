using System.Text.Json;
using Chummer.Run.Api.ViewModels;

namespace Chummer.Run.Api.Services;

public sealed class PublicPrivacyBoundaryService
{
    private const string PrivacyBoundariesRelativePath = ".codex-design/product/PRIVACY_AND_RETENTION_BOUNDARIES.md";
    private const string TrustContentRelativePath = ".codex-design/product/PUBLIC_TRUST_CONTENT.yaml";
    private const string DefaultContractName = "chummer.public_privacy_boundaries";
    private const string SourceDocument = "products/chummer/PRIVACY_AND_RETENTION_BOUNDARIES.md + products/chummer/PUBLIC_TRUST_CONTENT.yaml";
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };
    private static readonly BoundaryDomainSpec[] BoundaryDomains =
    [
        new(
            MarkdownHeading: "Support cases",
            Id: "support_case_truth",
            Label: "Support cases",
            PublicProjection: "Public pages can mention known issues and fix availability.",
            SignedInProjection: "Your account can show your own help history and follow-up."),
        new(
            MarkdownHeading: "Claim and install linkage",
            Id: "claim_install_linkage",
            Label: "Install linkage",
            PublicProjection: "Public pages show release status and install help.",
            SignedInProjection: "Your account can show linked installs and recovery context."),
        new(
            MarkdownHeading: "Survey and follow-up results",
            Id: "survey_follow_up",
            Label: "Survey follow-up",
            PublicProjection: "Public routes may summarize learned product changes after review.",
            SignedInProjection: "Signed-in routes may show that follow-up happened without replaying raw survey text."),
        new(
            MarkdownHeading: "Help tool traces",
            Id: "provider_traces",
            Label: "Help tools",
            PublicProjection: "Public help may show short answers and source links, not raw transcripts.",
            SignedInProjection: "Signed-in help may show the answer path without becoming the account record."),
        new(
            MarkdownHeading: "Hosted Build workspaces",
            Id: "hosted_build_workspaces",
            Label: "Hosted Build workspaces",
            PublicProjection: "No Hosted Build workspace content is public.",
            SignedInProjection: "Signed-in account surfaces may show only the owner's live hosted workspaces.",
            Status: PrivacyLaunchGate.Current.Status,
            ReviewRequired: PrivacyLaunchGate.Current.ReviewRequired,
            LaunchBlockingReason: PrivacyLaunchGate.Current.Reason)
    ];
    private static readonly BoundarySurfaceRuleSpec[] BoundarySurfaceRules =
    [
        new("Public surfaces", "public_surfaces", "Public surfaces"),
        new("Signed-in user surfaces", "signed_in_user_surfaces", "Signed-in user surfaces"),
        new("Help tool surfaces", "provider_backed_assistant_surfaces", "Help tools")
    ];

    private readonly PublicCanonFileLoader _canon;
    private readonly PublicRouteCatalogService _routes;
    private readonly object _documentLock = new();
    private PublicPrivacyBoundariesDocument? _cachedDocument;

    public PublicPrivacyBoundaryService(PublicCanonFileLoader canon, PublicRouteCatalogService routes)
    {
        _canon = canon;
        _routes = routes;
    }

    public PrivacyBoundaryPanelViewModel BuildPanel(string pageId)
    {
        var document = LoadDocument();
        var (primaryAction, secondaryAction) = BuildActions(pageId);
        var domains = (document.Domains ?? new List<PublicPrivacyBoundaryDomainDocument>())
            .Select(domain =>
            {
                BoundaryDomainSpec spec = RequireDomainSpec(domain.Id);
                return new PrivacyBoundaryDomainViewModel(
                    Label: RequireText(domain.Label, "privacy boundary domain label"),
                    Owner: RequireText(domain.Owner, $"privacy boundary domain '{domain.Id}' owner"),
                    RetentionSummary: RequireText(domain.RetentionSummary, $"privacy boundary domain '{domain.Id}' retention summary"),
                    RedactionSummary: RequireText(domain.RedactionSummary, $"privacy boundary domain '{domain.Id}' redaction summary"),
                    PublicProjection: RequireText(domain.PublicProjection, $"privacy boundary domain '{domain.Id}' public projection"),
                    SignedInProjection: RequireText(domain.SignedInProjection, $"privacy boundary domain '{domain.Id}' signed-in projection"),
                    Status: spec.Status,
                    ReviewRequired: spec.ReviewRequired,
                    LaunchBlockingReason: spec.LaunchBlockingReason);
            })
            .ToArray();
        BoundaryDomainSpec? blockingDomain = BoundaryDomains.FirstOrDefault(static domain => domain.ReviewRequired);

        return new PrivacyBoundaryPanelViewModel(
            Eyebrow: RequireText(document.Eyebrow, "privacy boundary eyebrow"),
            Heading: RequireText(document.Heading, "privacy boundary heading"),
            Summary: RequireText(document.Summary, "privacy boundary summary"),
            MicroProof: document.MicroProof?.ToArray() ?? Array.Empty<string>(),
            Domains: domains,
            SurfaceRules: (document.SurfaceRules ?? new List<PublicPrivacyBoundarySurfaceRuleDocument>())
                .Select(rule => new PrivacyBoundarySurfaceRuleViewModel(
                    Label: RequireText(rule.Label, $"privacy boundary surface rule '{rule.Id}' label"),
                    Summary: RequireText(rule.Summary, $"privacy boundary surface rule '{rule.Id}' summary"),
                    BlockedSummary: RequireText(rule.BlockedSummary, $"privacy boundary surface rule '{rule.Id}' blocked summary")))
                .ToArray(),
            PrimaryAction: primaryAction,
            SecondaryAction: secondaryAction,
            Status: blockingDomain?.Status ?? "documented",
            ReviewRequired: blockingDomain is not null,
            LaunchBlockingReason: blockingDomain?.LaunchBlockingReason);
    }

    public string LoadArtifactJson()
    {
        var document = LoadDocument();
        BoundaryDomainSpec? blockingDomain = BoundaryDomains.FirstOrDefault(static domain => domain.ReviewRequired);
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
                .Select(domain =>
                {
                    BoundaryDomainSpec spec = RequireDomainSpec(domain.Id);
                    return new PublicPrivacyBoundaryArtifactDomain(
                        Id: RequireText(domain.Id, "privacy boundary domain id"),
                        Label: RequireText(domain.Label, $"privacy boundary domain '{domain.Id}' label"),
                        Owner: RequireText(domain.Owner, $"privacy boundary domain '{domain.Id}' owner"),
                        RetentionSummary: RequireText(domain.RetentionSummary, $"privacy boundary domain '{domain.Id}' retention summary"),
                        RedactionSummary: RequireText(domain.RedactionSummary, $"privacy boundary domain '{domain.Id}' redaction summary"),
                        PublicProjection: RequireText(domain.PublicProjection, $"privacy boundary domain '{domain.Id}' public projection"),
                        SignedInProjection: RequireText(domain.SignedInProjection, $"privacy boundary domain '{domain.Id}' signed-in projection"),
                        Status: spec.Status,
                        ReviewRequired: spec.ReviewRequired,
                        LaunchBlockingReason: spec.LaunchBlockingReason);
                })
                .ToArray(),
            SurfaceRules: (document.SurfaceRules ?? new List<PublicPrivacyBoundarySurfaceRuleDocument>())
                .Select(rule => new PublicPrivacyBoundaryArtifactSurfaceRule(
                    Id: RequireText(rule.Id, "privacy boundary surface rule id"),
                    Label: RequireText(rule.Label, $"privacy boundary surface rule '{rule.Id}' label"),
                    Summary: RequireText(rule.Summary, $"privacy boundary surface rule '{rule.Id}' summary"),
                    BlockedSummary: RequireText(rule.BlockedSummary, $"privacy boundary surface rule '{rule.Id}' blocked summary")))
                .ToArray(),
            Status: blockingDomain?.Status ?? "documented",
            ReviewRequired: blockingDomain is not null,
            LaunchBlockingReason: blockingDomain?.LaunchBlockingReason,
            Scope: PrivacyLaunchGate.Current.Scope,
            CapabilityContractName: PrivacyLaunchGate.Current.CapabilityContractName,
            CapabilityContractVersion: PrivacyLaunchGate.Current.CapabilityContractVersion,
            Facts: PrivacyLaunchGate.Current.Facts,
            ProhibitedClaims: PrivacyLaunchGate.Current.ProhibitedClaims,
            BlocksLaunch: PrivacyLaunchGate.Current.BlocksReleaseSupportability,
            BlockedClaims: PrivacyLaunchGate.Current.BlockedClaims);

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
            _ => new TrustPageActionViewModel("Open contact", "/contact", "ghost")
        };

        _routes.ValidateRouteTarget(primary.Href, $"privacy boundary action '{primary.Label}'");
        _routes.ValidateRouteTarget(secondary.Href, $"privacy boundary action '{secondary.Label}'");
        return (primary, secondary);
    }

    private PublicPrivacyBoundariesDocument LoadDocument()
    {
        lock (_documentLock)
        {
            if (_cachedDocument is not null)
            {
                return _cachedDocument;
            }
        }

        var trust = _canon.LoadRequiredYaml<PublicTrustContentDocument>(TrustContentRelativePath);
        var privacyPage = (trust.TrustPages ?? new List<PublicTrustPageDocument>())
            .FirstOrDefault(static page => string.Equals(page.Id, "privacy", StringComparison.Ordinal))
            ?? throw new InvalidOperationException("public trust content is missing the privacy trust page.");

        var markdown = _canon.LoadRequiredText(PrivacyBoundariesRelativePath);
        var retentionDomains = ParseRetentionDomains(markdown);
        var surfaceRules = ParseSurfaceRules(markdown);

        var document = new PublicPrivacyBoundariesDocument
        {
            Product = "chummer",
            Surface = "public_privacy_boundaries",
            Version = 2,
            ContractName = DefaultContractName,
            AsOf = privacyPage.UpdatedDate ?? privacyPage.EffectiveDate ?? string.Empty,
            Eyebrow = "Privacy",
            Heading = "What Chummer stores, hides, and still needs review",
            Summary = "Chummer keeps account, install, help, feedback, and owner-scoped Hosted Build workspace data. This page separates approved retention rules from Hosted Build recovery and erasure policy that is still under review.",
            MicroProof = privacyPage.SummaryPoints ?? new List<string>(),
            Domains = BoundaryDomains
                .Select(spec => BuildDomain(spec, retentionDomains))
                .ToList(),
            SurfaceRules = BoundarySurfaceRules
                .Select(spec => BuildSurfaceRule(spec, surfaceRules))
                .ToList()
        };

        lock (_documentLock)
        {
            _cachedDocument ??= document;
            return _cachedDocument;
        }
    }

    private static PublicPrivacyBoundaryDomainDocument BuildDomain(
        BoundaryDomainSpec spec,
        IReadOnlyDictionary<string, RetentionDomainSection> sections)
    {
        if (!TryGetSection(sections, spec.MarkdownHeading, out var section))
        {
            throw new InvalidOperationException($"privacy canon is missing retention domain '{spec.MarkdownHeading}'.");
        }

        return new PublicPrivacyBoundaryDomainDocument
        {
            Id = spec.Id,
            Label = spec.Label,
            Owner = section.Owner,
            RetentionSummary = JoinBulletSummary(section.RetentionBullets),
            RedactionSummary = JoinBulletSummary(section.RedactionBullets),
            PublicProjection = spec.PublicProjection,
            SignedInProjection = spec.SignedInProjection
        };
    }

    private static PublicPrivacyBoundarySurfaceRuleDocument BuildSurfaceRule(
        BoundarySurfaceRuleSpec spec,
        IReadOnlyDictionary<string, IReadOnlyList<string>> sections)
    {
        if (!TryGetSection(sections, spec.MarkdownHeading, out var bullets))
        {
            throw new InvalidOperationException($"privacy canon is missing surface rule '{spec.MarkdownHeading}'.");
        }

        return new PublicPrivacyBoundarySurfaceRuleDocument
        {
            Id = spec.Id,
            Label = spec.Label,
            Summary = bullets.Count > 0 ? bullets[0] : throw new InvalidOperationException($"surface rule '{spec.MarkdownHeading}' is missing its summary bullet."),
            BlockedSummary = bullets.Count > 1 ? bullets[1] : throw new InvalidOperationException($"surface rule '{spec.MarkdownHeading}' is missing its blocked-summary bullet.")
        };
    }

    private static IReadOnlyDictionary<string, RetentionDomainSection> ParseRetentionDomains(string markdown)
    {
        var sections = new Dictionary<string, RetentionDomainSection>(StringComparer.Ordinal);
        string? currentTop = null;
        string? currentHeading = null;
        string? currentList = null;
        string? owner = null;
        List<string> retention = [];
        List<string> redaction = [];

        foreach (var rawLine in markdown.Split('\n'))
        {
            var line = rawLine.Trim();
            if (line.StartsWith("## ", StringComparison.Ordinal))
            {
                CommitRetentionSection();
                currentTop = line[3..].Trim();
                currentHeading = null;
                currentList = null;
                continue;
            }

            if (!string.Equals(currentTop, "Retention domains", StringComparison.Ordinal))
            {
                continue;
            }

            if (line.StartsWith("### ", StringComparison.Ordinal))
            {
                CommitRetentionSection();
                currentHeading = line[4..].Trim();
                currentList = null;
                owner = null;
                retention = [];
                redaction = [];
                continue;
            }

            if (string.IsNullOrWhiteSpace(currentHeading))
            {
                continue;
            }

            if (line.StartsWith("Owner:", StringComparison.Ordinal))
            {
                owner = NormalizeOwner(line["Owner:".Length..]);
                continue;
            }

            if (IsRetentionHeading(line))
            {
                currentList = "retention";
                continue;
            }

            if (string.Equals(line, "Redaction baseline:", StringComparison.Ordinal))
            {
                currentList = "redaction";
                continue;
            }

            if (line.StartsWith("* ", StringComparison.Ordinal))
            {
                if (string.Equals(currentList, "retention", StringComparison.Ordinal))
                {
                    retention.Add(line[2..].Trim());
                }
                else if (string.Equals(currentList, "redaction", StringComparison.Ordinal))
                {
                    redaction.Add(line[2..].Trim());
                }
            }
        }

        CommitRetentionSection();
        return sections;

        void CommitRetentionSection()
        {
            if (string.IsNullOrWhiteSpace(currentHeading))
            {
                return;
            }

            sections[currentHeading] = new RetentionDomainSection(
                string.IsNullOrWhiteSpace(owner)
                    ? throw new InvalidOperationException($"retention domain '{currentHeading}' is missing an owner.")
                    : owner,
                retention.ToArray(),
                redaction.ToArray());
        }
    }

    private static IReadOnlyDictionary<string, IReadOnlyList<string>> ParseSurfaceRules(string markdown)
    {
        var sections = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal);
        string? currentTop = null;
        string? currentHeading = null;
        List<string> bullets = [];

        foreach (var rawLine in markdown.Split('\n'))
        {
            var line = rawLine.Trim();
            if (line.StartsWith("## ", StringComparison.Ordinal))
            {
                CommitSurfaceRule();
                currentTop = line[3..].Trim();
                currentHeading = null;
                continue;
            }

            if (!string.Equals(currentTop, "Surface redaction rules", StringComparison.Ordinal))
            {
                continue;
            }

            if (line.StartsWith("### ", StringComparison.Ordinal))
            {
                CommitSurfaceRule();
                currentHeading = line[4..].Trim();
                bullets = [];
                continue;
            }

            if (string.IsNullOrWhiteSpace(currentHeading))
            {
                continue;
            }

            if (line.StartsWith("* ", StringComparison.Ordinal))
            {
                bullets.Add(line[2..].Trim());
            }
        }

        CommitSurfaceRule();
        return sections;

        void CommitSurfaceRule()
        {
            if (string.IsNullOrWhiteSpace(currentHeading))
            {
                return;
            }

            sections[currentHeading] = bullets.ToArray();
        }
    }

    private static string JoinBulletSummary(IReadOnlyList<string> bullets)
    {
        if (bullets.Count == 0)
        {
            throw new InvalidOperationException("privacy canon is missing required bullet content.");
        }

        return string.Join(" ", bullets);
    }

    private static bool IsRetentionHeading(string line)
        => string.Equals(line, "Retention posture:", StringComparison.Ordinal)
            || string.Equals(line, "Retention:", StringComparison.Ordinal);

    private static bool TryGetSection<T>(
        IReadOnlyDictionary<string, T> sections,
        string heading,
        out T section)
    {
        if (sections.TryGetValue(heading, out section!))
        {
            return true;
        }

        foreach (var alias in HeadingAliases(heading))
        {
            if (sections.TryGetValue(alias, out section!))
            {
                return true;
            }
        }

        section = default!;
        return false;
    }

    private static IReadOnlyList<string> HeadingAliases(string heading)
        => heading switch
        {
            "Support cases" => ["Support-case truth"],
            "Help tool traces" => ["Help and assistant service traces", "Help-service logs and answer notes"],
            "Help and assistant service traces" => ["Help-service logs and answer notes"],
            "Help tool surfaces" => ["Help and assistant surfaces"],
            _ => Array.Empty<string>()
        };

    private static string RequireText(string? value, string description)
        => string.IsNullOrWhiteSpace(value)
            ? throw new InvalidOperationException($"{description} is missing required text.")
            : value;

    private static string NormalizeOwner(string value)
        => value.Replace("`", string.Empty, StringComparison.Ordinal).Trim();

    private static BoundaryDomainSpec RequireDomainSpec(string? id)
        => BoundaryDomains.FirstOrDefault(domain => string.Equals(domain.Id, id, StringComparison.Ordinal))
            ?? throw new InvalidOperationException($"privacy boundary domain '{id}' has no projection specification.");

    private sealed record BoundaryDomainSpec(
        string MarkdownHeading,
        string Id,
        string Label,
        string PublicProjection,
        string SignedInProjection,
        string Status = "documented",
        bool ReviewRequired = false,
        string? LaunchBlockingReason = null);

    private sealed record BoundarySurfaceRuleSpec(
        string MarkdownHeading,
        string Id,
        string Label);

    private sealed record RetentionDomainSection(
        string Owner,
        IReadOnlyList<string> RetentionBullets,
        IReadOnlyList<string> RedactionBullets);

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
        IReadOnlyList<PublicPrivacyBoundaryArtifactSurfaceRule> SurfaceRules,
        string Status,
        bool ReviewRequired,
        string? LaunchBlockingReason,
        string Scope,
        string CapabilityContractName,
        int CapabilityContractVersion,
        IReadOnlyList<string> Facts,
        IReadOnlyList<string> ProhibitedClaims,
        bool BlocksLaunch,
        IReadOnlyList<string> BlockedClaims);

    private sealed record PublicPrivacyBoundaryArtifactDomain(
        string Id,
        string Label,
        string Owner,
        string RetentionSummary,
        string RedactionSummary,
        string PublicProjection,
        string SignedInProjection,
        string Status,
        bool ReviewRequired,
        string? LaunchBlockingReason);

    private sealed record PublicPrivacyBoundaryArtifactSurfaceRule(
        string Id,
        string Label,
        string Summary,
        string BlockedSummary);
}
