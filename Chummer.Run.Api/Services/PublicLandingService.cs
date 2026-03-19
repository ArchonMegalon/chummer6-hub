using System.Text.RegularExpressions;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class PublicLandingService
{
    private const string ManifestRelativePath = ".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml";
    private const string FeatureRegistryRelativePath = ".codex-design/product/PUBLIC_FEATURE_REGISTRY.yaml";
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
        if (!File.Exists(manifestPath))
        {
            throw new FileNotFoundException($"public landing manifest not found: {manifestPath}");
        }

        if (!File.Exists(featureRegistryPath))
        {
            throw new FileNotFoundException($"public feature registry not found: {featureRegistryPath}");
        }

        var manifest = File.ReadAllLines(manifestPath);
        var featureRegistry = File.ReadAllLines(featureRegistryPath);

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
            SecondaryHighlights: ParseStringList(manifest, "secondary_highlights").ToArray(),
            PublicRoutes: ParseMapList(manifest, "public_routes")
                .Select(static item => new PublicLandingRouteDto(
                    Path: Required(item, "path"),
                    Title: Required(item, "title"),
                    Audience: Required(item, "audience"),
                    Purpose: Required(item, "purpose")))
                .ToArray(),
            RegisteredRoutes: ParseMapList(manifest, "registered_routes")
                .Select(static item => new PublicLandingRouteDto(
                    Path: Required(item, "path"),
                    Title: Required(item, "title"),
                    Audience: Required(item, "audience"),
                    Purpose: Required(item, "purpose")))
                .ToArray(),
            Sections: ParseMapList(manifest, "sections")
                .Select(static item => new PublicLandingSectionDto(
                    Id: Required(item, "id"),
                    Title: Required(item, "title"),
                    Audience: Required(item, "audience"),
                    Route: Required(item, "route")))
                .ToArray(),
            RegisteredOverlays: ParseMapList(manifest, "registered_overlays")
                .Select(static item => new PublicLandingOverlayDto(
                    Id: Required(item, "id"),
                    Path: Required(item, "path"),
                    Title: Required(item, "title"),
                    Summary: Required(item, "summary")))
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
                    Pain: Optional(item, "pain"),
                    Payoff: Optional(item, "payoff")))
                .ToArray());
    }

    public IReadOnlyList<PublicFeatureCardDto> CardsForBucket(PublicLandingSurfaceDto surface, string bucket)
        => surface.FeatureCards
            .Where(card => string.Equals(card.Bucket, bucket, StringComparison.Ordinal))
            .ToArray();

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
