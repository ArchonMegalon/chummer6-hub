using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;

namespace Chummer.Run.Api.Services;

public sealed class PublicSignalProjectionService
{
    private const string RegistryRelativePath = "products/chummer/PUBLIC_FEEDBACK_AND_CONTENT_REGISTRY.yaml";
    private const string BridgeRelativePath = "products/chummer/PUBLIC_SIGNAL_FEEDBACK_ROADMAP_BRIDGE.md";
    private const string PipelineRelativePath = "products/chummer/PUBLIC_SIGNAL_TO_CANON_PIPELINE.md";
    private static readonly IDeserializer Deserializer = new DeserializerBuilder()
        .WithNamingConvention(UnderscoredNamingConvention.Instance)
        .IgnoreUnmatchedProperties()
        .Build();

    private readonly PublicCanonFileLoader _canon;
    private readonly PublicRouteCatalogService _routes;
    private readonly PublicSignalToCanonPacketService _packets;

    public PublicSignalProjectionService(
        PublicCanonFileLoader canon,
        PublicRouteCatalogService routes,
        PublicSignalToCanonPacketService packets)
    {
        _canon = canon;
        _routes = routes;
        _packets = packets;
    }

    public PublicSignalProjectionPacketViewModel? BuildPacket(string publicPath)
    {
        var document = LoadDocument();
        var normalizedPublicPath = PublicRouteCatalog.NormalizeRoute(publicPath);
        var surface = (document.Surfaces ?? new List<PublicFeedbackSurfaceDocument>())
            .FirstOrDefault(item =>
                string.Equals(
                    PublicRouteCatalog.NormalizeRoute(item.PublicPath ?? string.Empty),
                    normalizedPublicPath,
                    StringComparison.OrdinalIgnoreCase));
        if (surface is null)
        {
            return null;
        }

        _routes.ValidateRouteTarget(surface.PublicPath, $"public signal surface '{surface.Key}'");
        _routes.ValidateRouteTarget(surface.FallbackPath, $"public signal fallback '{surface.Key}'");
        var packet = ResolveJourneyProofPacket(normalizedPublicPath);

        return new PublicSignalProjectionPacketViewModel(
            Eyebrow: "Projection packet",
            Heading: ResolveHeading(surface),
            Summary: BuildSummary(surface),
            Vendor: ResolveProjectionLabel(surface),
            Role: HumanizeToken(surface.Role, "Public projection"),
            TruthPosture: HumanizeToken(surface.TruthPosture, "Projection only"),
            PublicPath: RequireText(surface.PublicPath, $"public signal surface '{surface.Key}' public_path"),
            FallbackPath: RequireText(surface.FallbackPath, $"public signal surface '{surface.Key}' fallback_path"),
            PolicyStatus: document.PolicyStatus,
            CoreRule: document.CoreRule,
            AuthorityFlow: document.AuthorityFlow,
            DecisionRoutes: (surface.RoutesTo ?? new List<string>())
                .Select(item => HumanizeToken(item, item))
                .ToArray(),
            CanonicalSources: (surface.CanonicalSource ?? new List<string>())
                .Where(static item => !string.IsNullOrWhiteSpace(item))
                .ToArray(),
            Forbidden: (surface.Forbidden ?? new List<string>())
                .Where(static item => !string.IsNullOrWhiteSpace(item))
                .Select(item => HumanizeToken(item, item))
                .ToArray(),
            CloseoutRequirements: ResolveCloseoutRequirements(document, surface),
            PublicWarning: document.PublicWarning,
            BoardTargets: document.BoardTargets,
            JourneyProofEventRefs: packet?.JourneyProofEventRefs ?? Array.Empty<JourneyProofEventRef>(),
            PolicySource: RequireText(surface.PolicySource, $"public signal surface '{surface.Key}' policy_source"),
            PipelineSource: PipelineRelativePath,
            RegistrySource: RegistryRelativePath);
    }

    private SignalToCanonPacketProjection? ResolveJourneyProofPacket(string normalizedPublicPath)
    {
        string? surfaceId = normalizedPublicPath switch
        {
            "/feedback" => "feedback",
            "/roadmap" => "roadmap",
            "/changelog" => "changelog",
            _ => null
        };

        if (surfaceId is null)
        {
            return null;
        }

        return _packets.Build().Packets.FirstOrDefault(packet =>
            string.Equals(packet.SurfaceId, surfaceId, StringComparison.OrdinalIgnoreCase));
    }

    private SignalProjectionDocument LoadDocument()
    {
        var registry = Deserializer.Deserialize<PublicFeedbackRegistryDocument>(_canon.LoadRequiredText(RegistryRelativePath))
            ?? throw new InvalidOperationException($"canon file '{RegistryRelativePath}' could not be deserialized.");
        string bridge = _canon.LoadRequiredText(BridgeRelativePath);
        string pipeline = _canon.LoadRequiredText(PipelineRelativePath);

        return new SignalProjectionDocument(
            Surfaces: registry.Surfaces ?? new List<PublicFeedbackSurfaceDocument>(),
            ProductLiftShippedRequirements: (
                registry.CloseoutRequirements?.PublicShippedItem?.Required
                ?? registry.CloseoutRequirements?.ProductliftShippedItem?.Required
                ?? [])
                .ToArray(),
            PolicyStatus: ExtractSectionParagraph(bridge, "Status"),
            CoreRule: ExtractSectionParagraph(pipeline, "Core rule"),
            AuthorityFlow: ExtractFirstCodeBlock(bridge, "Authority rule"),
            PublicWarning: ExtractBlockQuote(bridge, "Required public warning:"),
            BoardTargets: ExtractBulletList(bridge, "First board set", "Initial public signal boards:"));
    }

    private static string ResolveHeading(PublicFeedbackSurfaceDocument surface)
        => NormalizeKey(surface.Role) switch
        {
            "public_feedback_and_voting" => "Hosted public feedback remains projection-only and first-party-governed.",
            "roadmap_projection" => "Hosted roadmap cards stay downstream of Chummer-owned planning truth.",
            "changelog_projection_and_voter_notification" => "Hosted shipped closeout stays downstream of Chummer-owned availability proof.",
            _ => "Hosted public signal stays bounded by Chummer-owned truth."
        };

    private static string ResolveProjectionLabel(PublicFeedbackSurfaceDocument surface)
    {
        string vendor = (surface.Vendor ?? string.Empty).Trim();
        if (!string.IsNullOrWhiteSpace(vendor))
        {
            return vendor;
        }

        return NormalizeKey(surface.Role) switch
        {
            "public_feedback_and_voting" => "Public feedback board",
            "roadmap_projection" => "Roadmap projection",
            "changelog_projection_and_voter_notification" => "Shipped closeout board",
            _ => "Hosted projection"
        };
    }

    private static string BuildSummary(PublicFeedbackSurfaceDocument surface)
    {
        string publicPath = RequireText(surface.PublicPath, $"public signal surface '{surface.Key}' public_path");
        string fallbackPath = RequireText(surface.FallbackPath, $"public signal surface '{surface.Key}' fallback_path");
        string truthPosture = HumanizeToken(surface.TruthPosture, "projection only").ToLowerInvariant();
        return $"Hosted projection may mirror this route, but the posture stays {truthPosture}. If hosted projection is unavailable or misconfigured, the first-party path falls back to {fallbackPath} instead of hiding {publicPath}.";
    }

    private static IReadOnlyList<string> ResolveCloseoutRequirements(SignalProjectionDocument document, PublicFeedbackSurfaceDocument surface)
    {
        return string.Equals(NormalizeKey(surface.Key), "public_changelog", StringComparison.OrdinalIgnoreCase)
            ? document.ProductLiftShippedRequirements
                .Select(item => HumanizeToken(item, item))
                .ToArray()
            : Array.Empty<string>();
    }

    private static string ExtractSectionParagraph(string markdown, string heading)
    {
        string headingMarker = $"## {heading}";
        bool inSection = false;

        foreach (var rawLine in markdown.Split('\n'))
        {
            string line = rawLine.Trim();
            if (line.StartsWith("## ", StringComparison.Ordinal))
            {
                if (inSection)
                {
                    break;
                }

                inSection = string.Equals(line, headingMarker, StringComparison.Ordinal);
                continue;
            }

            if (!inSection || string.IsNullOrWhiteSpace(line) || line.StartsWith("```", StringComparison.Ordinal))
            {
                continue;
            }

            return line;
        }

        throw new InvalidOperationException($"markdown canon is missing section paragraph '{headingMarker}'.");
    }

    private static IReadOnlyList<string> ExtractFirstCodeBlock(string markdown, string heading)
    {
        string headingMarker = $"## {heading}";
        bool inSection = false;
        bool inCodeBlock = false;
        List<string> lines = [];

        foreach (var rawLine in markdown.Split('\n'))
        {
            string line = rawLine.Trim();
            if (line.StartsWith("## ", StringComparison.Ordinal))
            {
                if (inSection && lines.Count > 0)
                {
                    break;
                }

                inSection = string.Equals(line, headingMarker, StringComparison.Ordinal);
                inCodeBlock = false;
                continue;
            }

            if (!inSection)
            {
                continue;
            }

            if (line.StartsWith("```", StringComparison.Ordinal))
            {
                inCodeBlock = !inCodeBlock;
                if (!inCodeBlock && lines.Count > 0)
                {
                    break;
                }

                continue;
            }

            if (inCodeBlock && !string.IsNullOrWhiteSpace(line))
            {
                lines.Add(line);
            }
        }

        if (lines.Count == 0)
        {
            throw new InvalidOperationException($"markdown canon is missing authority flow code block for '{headingMarker}'.");
        }

        return lines;
    }

    private static string ExtractBlockQuote(string markdown, string marker)
    {
        bool inBlock = false;
        List<string> lines = [];

        foreach (var rawLine in markdown.Split('\n'))
        {
            string line = rawLine.Trim();
            if (!inBlock)
            {
                if (string.Equals(line, marker, StringComparison.Ordinal))
                {
                    inBlock = true;
                }

                continue;
            }

            if (line.StartsWith('>'))
            {
                lines.Add(line.TrimStart('>', ' '));
                continue;
            }

            if (lines.Count > 0)
            {
                break;
            }
        }

        if (lines.Count == 0)
        {
            throw new InvalidOperationException($"markdown canon is missing quoted warning block after '{marker}'.");
        }

        return string.Join(" ", lines);
    }

    private static IReadOnlyList<string> ExtractBulletList(string markdown, string heading, string introLine)
    {
        string headingMarker = $"## {heading}";
        bool inSection = false;
        bool listStarted = false;
        List<string> items = [];

        foreach (var rawLine in markdown.Split('\n'))
        {
            string line = rawLine.Trim();
            if (line.StartsWith("## ", StringComparison.Ordinal))
            {
                if (inSection && items.Count > 0)
                {
                    break;
                }

                inSection = string.Equals(line, headingMarker, StringComparison.Ordinal);
                listStarted = false;
                continue;
            }

            if (!inSection)
            {
                continue;
            }

            if (!listStarted)
            {
                if (string.Equals(line, introLine, StringComparison.Ordinal))
                {
                    listStarted = true;
                }

                continue;
            }

            if (line.StartsWith("- ", StringComparison.Ordinal))
            {
                items.Add(line[2..].Trim());
                continue;
            }

            if (items.Count > 0)
            {
                break;
            }
        }

        if (items.Count == 0)
        {
            throw new InvalidOperationException($"markdown canon is missing bullet list for '{headingMarker}'.");
        }

        return items;
    }

    private static string HumanizeToken(string? value, string fallback)
        => string.IsNullOrWhiteSpace(value)
            ? fallback
            : System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(value.Replace('_', ' ').Replace('-', ' '));

    private static string NormalizeKey(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? string.Empty
            : value.Trim().ToLowerInvariant();

    private static string RequireText(string? value, string description)
        => string.IsNullOrWhiteSpace(value)
            ? throw new InvalidOperationException($"{description} is missing.")
            : value.Trim();

    private sealed record SignalProjectionDocument(
        IReadOnlyList<PublicFeedbackSurfaceDocument> Surfaces,
        IReadOnlyList<string> ProductLiftShippedRequirements,
        string PolicyStatus,
        string CoreRule,
        IReadOnlyList<string> AuthorityFlow,
        string PublicWarning,
        IReadOnlyList<string> BoardTargets);

    private sealed class PublicFeedbackRegistryDocument
    {
        public List<PublicFeedbackSurfaceDocument>? Surfaces { get; init; }
        public PublicFeedbackCloseoutRequirementsDocument? CloseoutRequirements { get; init; }
    }

    private sealed class PublicFeedbackSurfaceDocument
    {
        public string? Key { get; init; }
        public string? Vendor { get; init; }
        public string? PolicySource { get; init; }
        public string? PublicPath { get; init; }
        public string? FallbackPath { get; init; }
        public string? Role { get; init; }
        public string? TruthPosture { get; init; }
        public List<string>? RoutesTo { get; init; }
        public List<string>? CanonicalSource { get; init; }
        public List<string>? Forbidden { get; init; }
    }

    private sealed class PublicFeedbackCloseoutRequirementsDocument
    {
        public PublicFeedbackRequirementDocument? PublicShippedItem { get; init; }
        public PublicFeedbackRequirementDocument? ProductliftShippedItem { get; init; }
    }

    private sealed class PublicFeedbackRequirementDocument
    {
        public List<string>? Required { get; init; }
    }
}
