using System.Text.RegularExpressions;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class PublicLandingService
{
    private const string ManifestRelativePath = ".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml";
    private const string FeatureRegistryRelativePath = ".codex-design/product/PUBLIC_FEATURE_REGISTRY.yaml";
    private const string AssetRegistryRelativePath = ".codex-design/product/PUBLIC_LANDING_ASSET_REGISTRY.yaml";
    private readonly IConfiguration _configuration;
    private readonly ILogger<PublicLandingService> _logger;

    public PublicLandingService(IConfiguration configuration, ILogger<PublicLandingService> logger)
    {
        _configuration = configuration;
        _logger = logger;
    }

    public PublicLandingSurfaceDto LoadSurface()
    {
        var repoRoot = ResolveRepoRoot();
        var manifestPath = Path.Combine(repoRoot, ManifestRelativePath);
        var featureRegistryPath = Path.Combine(repoRoot, FeatureRegistryRelativePath);
        var assetRegistryPath = Path.Combine(repoRoot, AssetRegistryRelativePath);
        if (!File.Exists(manifestPath))
        {
            throw new FileNotFoundException($"public landing manifest not found: {manifestPath}");
        }

        if (!File.Exists(featureRegistryPath))
        {
            throw new FileNotFoundException($"public feature registry not found: {featureRegistryPath}");
        }

        if (!File.Exists(assetRegistryPath))
        {
            throw new FileNotFoundException($"public landing asset registry not found: {assetRegistryPath}");
        }

        var manifest = File.ReadAllLines(manifestPath);
        var featureRegistry = File.ReadAllLines(featureRegistryPath);
        var assetRegistry = File.ReadAllLines(assetRegistryPath);

        return new PublicLandingSurfaceDto(
            Product: RequiredScalar(manifest, "product"),
            Surface: RequiredScalar(manifest, "surface"),
            Version: ParseInt(RequiredScalar(manifest, "version"), "version"),
            Headline: RequiredScalar(manifest, "headline"),
            Subhead: RequiredScalar(manifest, "subhead"),
            ProofLine: RequiredScalar(manifest, "proof_line"),
            NoProviderNames: ParseBool(RequiredScalar(manifest, "no_provider_names")),
            NoLtdNames: ParseBool(RequiredScalar(manifest, "no_ltd_names")),
            HeroCtas: ParseMapList(manifest, "hero_ctas")
                .Select(static item => new PublicLandingActionDto(
                    Label: Required(item, "label"),
                    Href: Required(item, "href"),
                    Emphasis: Required(item, "emphasis")))
                .ToArray(),
            GuestShellActions: ParseMapList(manifest, "guest_shell_actions")
                .Select(static item => new PublicLandingActionDto(
                    Label: Required(item, "label"),
                    Href: Required(item, "href"),
                    Emphasis: Required(item, "emphasis")))
                .ToArray(),
            SecondaryHighlights: ParseStringList(manifest, "secondary_highlights").ToArray(),
            PublicRoutes: ParseMapList(manifest, "public_routes")
                .Select(ParseRoute)
                .ToArray(),
            AuthRoutes: ParseMapList(manifest, "auth_routes")
                .Select(ParseRoute)
                .ToArray(),
            RegisteredRoutes: ParseMapList(manifest, "registered_routes")
                .Select(ParseRoute)
                .ToArray(),
            Sections: ParseMapList(manifest, "sections")
                .Select(static item => new PublicLandingSectionDto(
                    Id: Required(item, "id"),
                    Title: Required(item, "title"),
                    Audience: Required(item, "audience"),
                    Route: Required(item, "route"),
                    AssetSlot: Optional(item, "asset_slot")))
                .ToArray(),
            RegisteredOverlays: ParseMapList(manifest, "registered_overlays")
                .Select(static item => new PublicLandingOverlayDto(
                    Id: Required(item, "id"),
                    Path: Required(item, "path"),
                    Title: Required(item, "title"),
                    Summary: Required(item, "summary")))
                .ToArray(),
            Assets: ParseMapList(assetRegistry, "assets")
                .Select(ParseAsset)
                .ToArray(),
            FooterCanonicalSource: RequiredScalar(manifest, "footer_canonical_source"),
            FooterGeneratedNote: RequiredScalar(manifest, "footer_generated_note"),
            FeatureCards: ParseMapList(featureRegistry, "cards")
                .Select(static item => new PublicFeatureCardDto(
                    Id: Required(item, "id"),
                    Bucket: Required(item, "bucket"),
                    Title: Required(item, "title"),
                    Summary: Required(item, "summary"),
                    Href: Required(item, "href"),
                    Badge: Required(item, "badge"),
                    Audience: Required(item, "audience"),
                    ImageFamily: Required(item, "image_family"),
                    AssetSlot: Optional(item, "asset_slot") ?? $"scene_{Required(item, "image_family")}",
                    CtaKind: Optional(item, "cta_kind") ?? "route",
                    RenderMode: Optional(item, "render_mode") ?? "action",
                    DetailRoute: Optional(item, "detail_route"),
                    FallbackRoute: Optional(item, "fallback_route"),
                    FallbackLabel: Optional(item, "fallback_label"),
                    GuestHref: Optional(item, "guest_href"),
                    RegisteredHref: Optional(item, "registered_href"),
                    ExternalOk: ParseOptionalBool(item, "external_ok") ?? false,
                    SelfLinkAllowed: ParseOptionalBool(item, "self_link_allowed") ?? false,
                    Pain: Optional(item, "pain"),
                    Payoff: Optional(item, "payoff")))
                .ToArray());
    }

    public IReadOnlyList<PublicFeatureCardDto> CardsForBucket(PublicLandingSurfaceDto surface, string bucket)
        => surface.FeatureCards
            .Where(card => string.Equals(card.Bucket, bucket, StringComparison.Ordinal))
            .ToArray();

    private static PublicLandingRouteDto ParseRoute(Dictionary<string, string> item)
        => new(
            Path: Required(item, "path"),
            Title: Required(item, "title"),
            Audience: Required(item, "audience"),
            Purpose: Required(item, "purpose"),
            RequiresAuth: ParseOptionalBool(item, "requires_auth") ?? false,
            GuestFallback: Optional(item, "guest_fallback"),
            MustExist: ParseOptionalBool(item, "must_exist") ?? true,
            PlaceholderAllowed: ParseOptionalBool(item, "placeholder_allowed") ?? false,
            PlaceholderRequirements: Optional(item, "placeholder_requirements"));

    private static PublicLandingAssetDto ParseAsset(Dictionary<string, string> item)
        => new(
            AssetSlot: Required(item, "asset_slot"),
            SectionId: Optional(item, "section_id"),
            MediaKind: Required(item, "media_kind"),
            PosterUrl: Optional(item, "poster_url"),
            MobilePosterUrl: Optional(item, "mobile_poster_url"),
            LoopUrl: Optional(item, "loop_url"),
            Alt: Required(item, "alt"),
            Caption: Required(item, "caption"),
            MotionPolicy: Required(item, "motion_policy"),
            FallbackStyle: Required(item, "fallback_style"));

    private string ResolveRepoRoot()
    {
        var configured = _configuration["CHUMMER_PUBLIC_CANON_ROOT"];
        var candidates = new[]
        {
            configured,
            Directory.GetCurrentDirectory(),
            AppContext.BaseDirectory,
            Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..")),
            "/docker/chummercomplete/chummer.run-services"
        }
        .Where(static path => !string.IsNullOrWhiteSpace(path))
        .Select(static path => Path.GetFullPath(path!))
        .Distinct(StringComparer.OrdinalIgnoreCase);

        foreach (var candidate in candidates)
        {
            if (File.Exists(Path.Combine(candidate, ManifestRelativePath)))
            {
                return candidate;
            }
        }

        throw new DirectoryNotFoundException("Unable to resolve a repo root that contains the mirrored public landing manifest.");
    }

    private static string RequiredScalar(IReadOnlyList<string> lines, string key)
        => OptionalScalar(lines, key) ?? throw new InvalidOperationException($"required landing scalar missing: {key}");

    private static string? OptionalScalar(IReadOnlyList<string> lines, string key)
    {
        foreach (var rawLine in lines)
        {
            var line = StripComment(rawLine);
            if (Indent(line) != 0 || string.IsNullOrWhiteSpace(line))
            {
                continue;
            }

            if (!line.StartsWith($"{key}:", StringComparison.Ordinal))
            {
                continue;
            }

            var value = line[(key.Length + 1)..].Trim();
            return string.IsNullOrWhiteSpace(value) ? null : Unquote(value);
        }

        return null;
    }

    private static bool? ParseOptionalBool(Dictionary<string, string> item, string key)
        => item.TryGetValue(key, out var value)
            ? ParseBool(value)
            : null;

    private static IReadOnlyList<string> ParseStringList(IReadOnlyList<string> lines, string sectionName)
    {
        var results = new List<string>();
        var insideSection = false;
        foreach (var rawLine in lines)
        {
            var line = StripComment(rawLine);
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }

            var indent = Indent(line);
            var trimmed = line.Trim();
            if (indent == 0)
            {
                if (string.Equals(trimmed, $"{sectionName}:", StringComparison.Ordinal))
                {
                    insideSection = true;
                    continue;
                }

                if (insideSection)
                {
                    break;
                }
            }

            if (!insideSection || indent != 2 || !trimmed.StartsWith("- ", StringComparison.Ordinal))
            {
                continue;
            }

            results.Add(Unquote(trimmed[2..].Trim()));
        }

        return results;
    }

    private static IReadOnlyList<Dictionary<string, string>> ParseMapList(IReadOnlyList<string> lines, string sectionName)
    {
        var results = new List<Dictionary<string, string>>();
        var insideSection = false;
        Dictionary<string, string>? current = null;

        foreach (var rawLine in lines)
        {
            var line = StripComment(rawLine);
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }

            var indent = Indent(line);
            var trimmed = line.Trim();
            if (indent == 0)
            {
                if (string.Equals(trimmed, $"{sectionName}:", StringComparison.Ordinal))
                {
                    insideSection = true;
                    current = null;
                    continue;
                }

                if (insideSection)
                {
                    break;
                }
            }

            if (!insideSection)
            {
                continue;
            }

            if (indent == 2 && trimmed.StartsWith("- ", StringComparison.Ordinal))
            {
                current = new Dictionary<string, string>(StringComparer.Ordinal);
                results.Add(current);
                var inline = trimmed[2..].Trim();
                if (!string.IsNullOrWhiteSpace(inline))
                {
                    ParseKeyValueInto(current, inline);
                }

                continue;
            }

            if (indent >= 4 && current is not null)
            {
                ParseKeyValueInto(current, trimmed);
            }
        }

        return results;
    }

    private static void ParseKeyValueInto(Dictionary<string, string> target, string line)
    {
        var separator = line.IndexOf(':');
        if (separator <= 0)
        {
            return;
        }

        var key = line[..separator].Trim();
        var value = line[(separator + 1)..].Trim();
        if (string.IsNullOrWhiteSpace(key))
        {
            return;
        }

        target[key] = Unquote(value);
    }

    private static string StripComment(string line)
    {
        if (string.IsNullOrWhiteSpace(line))
        {
            return line;
        }

        var commentIndex = line.IndexOf(" #", StringComparison.Ordinal);
        return commentIndex >= 0 ? line[..commentIndex] : line;
    }

    private static int Indent(string line)
    {
        var count = 0;
        while (count < line.Length && line[count] == ' ')
        {
            count++;
        }

        return count;
    }

    private static string Unquote(string value)
    {
        var trimmed = value.Trim();
        if (trimmed.Length >= 2
            && ((trimmed[0] == '"' && trimmed[^1] == '"')
                || (trimmed[0] == '\'' && trimmed[^1] == '\'')))
        {
            return trimmed[1..^1];
        }

        return trimmed;
    }

    private static string Required(IReadOnlyDictionary<string, string> values, string key)
        => Optional(values, key) ?? throw new InvalidOperationException($"required landing field missing: {key}");

    private static string? Optional(IReadOnlyDictionary<string, string> values, string key)
        => values.TryGetValue(key, out var value) && !string.IsNullOrWhiteSpace(value) ? value : null;

    private static int ParseInt(string value, string name)
        => int.TryParse(value, out var parsed)
            ? parsed
            : throw new InvalidOperationException($"landing integer field '{name}' is invalid: {value}");

    private static bool ParseBool(string value)
        => bool.TryParse(value, out var parsed)
            ? parsed
            : throw new InvalidOperationException($"landing boolean field is invalid: {value}");
}
