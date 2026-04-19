namespace Chummer.Run.Api.Services;

public sealed record PublicRouteCatalog(
    IReadOnlyList<string> PublicRoutes,
    IReadOnlyList<string> AuthRoutes,
    IReadOnlyList<string> RegisteredRoutes)
{
    private static readonly HashSet<string> RuntimeCompatibilityRoutes = new(StringComparer.OrdinalIgnoreCase)
    {
        "/artifacts/campaign-primer-video",
        "/artifacts/mission-brief-video"
    };

    public IReadOnlySet<string> AllowedRoutes { get; } = PublicRoutes
        .Concat(AuthRoutes)
        .Concat(RegisteredRoutes)
        .Select(static route => NormalizeRoute(route))
        .ToHashSet(StringComparer.OrdinalIgnoreCase);

    public static string NormalizeRoute(string route)
    {
        var trimmed = route.Trim();
        var hash = trimmed.IndexOf('#');
        if (hash >= 0)
        {
            trimmed = trimmed[..hash];
        }

        var query = trimmed.IndexOf('?');
        if (query >= 0)
        {
            trimmed = trimmed[..query];
        }

        return string.IsNullOrWhiteSpace(trimmed) ? "/" : trimmed;
    }

    public bool Contains(string route)
        => Contains(NormalizeRoute(route), AllowedRoutes);

    public static bool Contains(string normalizedRoute, IReadOnlySet<string> allowedRoutes)
        => allowedRoutes.Contains(normalizedRoute) || RuntimeCompatibilityRoutes.Contains(normalizedRoute);
}

public sealed class PublicRouteCatalogService
{
    private const string ManifestRelativePath = ".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml";
    private readonly PublicCanonFileLoader _canon;
    private readonly Lazy<PublicRouteCatalog> _catalog;

    public PublicRouteCatalogService(PublicCanonFileLoader canon)
    {
        _canon = canon;
        _catalog = new Lazy<PublicRouteCatalog>(LoadCore);
    }

    public PublicRouteCatalog Load()
        => _catalog.Value;

    private PublicRouteCatalog LoadCore()
    {
        var manifest = _canon.LoadRequiredYaml<PublicLandingManifestDocument>(ManifestRelativePath);
        return new PublicRouteCatalog(
            PublicRoutes: (manifest.PublicRoutes ?? new List<PublicLandingRouteDocument>())
                .Select(static route => route.Path)
                .ToArray(),
            AuthRoutes: (manifest.AuthRoutes ?? new List<PublicLandingRouteDocument>())
                .Select(static route => route.Path)
                .ToArray(),
            RegisteredRoutes: (manifest.RegisteredRoutes ?? new List<PublicLandingRouteDocument>())
                .Select(static route => route.Path)
                .ToArray());
    }

    public void ValidateRouteTarget(string? href, string description)
    {
        if (string.IsNullOrWhiteSpace(href))
        {
            throw new InvalidOperationException($"{description} is missing an href.");
        }

        if (PublicUrlPolicy.IsExternalHref(href))
        {
            return;
        }

        var allowedRoutes = Load().AllowedRoutes;
        var normalized = PublicRouteCatalog.NormalizeRoute(href);
        if (!PublicRouteCatalog.Contains(normalized, allowedRoutes))
        {
            throw new InvalidOperationException($"{description} points at missing route '{href}'.");
        }
    }
}
