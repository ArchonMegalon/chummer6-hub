namespace Chummer.Run.Api.Services;

public sealed record PublicNavigationLink(
    string Label,
    string Href);

public sealed record PublicNavigationModel(
    IReadOnlyList<PublicNavigationLink> Primary,
    IReadOnlyList<PublicNavigationLink> Secondary,
    IReadOnlyList<PublicNavigationLink> Utility);

public sealed class PublicNavigationService
{
    private const string NavigationRelativePath = ".codex-design/product/PUBLIC_NAVIGATION.yaml";
    private readonly PublicCanonFileLoader _canon;
    private readonly PublicRouteCatalogService _routes;

    public PublicNavigationService(PublicCanonFileLoader canon, PublicRouteCatalogService routes)
    {
        _canon = canon;
        _routes = routes;
    }

    public PublicNavigationModel LoadNavigation()
    {
        var document = _canon.LoadRequiredYaml<PublicNavigationDocument>(NavigationRelativePath);
        return new PublicNavigationModel(
            Primary: BuildLinks(document.PrimaryNav, "primary navigation"),
            Secondary: BuildLinks(document.SecondaryNav, "secondary navigation"),
            Utility: BuildLinks(document.UtilityNav, "utility navigation"));
    }

    private IReadOnlyList<PublicNavigationLink> BuildLinks(IReadOnlyList<PublicNavigationLinkDocument>? links, string group)
        => (links ?? new List<PublicNavigationLinkDocument>())
            .Select(link =>
            {
                _routes.ValidateRouteTarget(link.Href, $"{group} link '{link.Label}'");
                return new PublicNavigationLink(link.Label, link.Href);
            })
            .ToArray();
}
