namespace Chummer.Run.Api.Services;

public sealed record PublicNavigationLink(
    string Label,
    string Href);

public sealed record PublicNavigationModel(
    IReadOnlyList<PublicNavigationLink> Primary,
    IReadOnlyList<PublicNavigationLink> Secondary,
    IReadOnlyList<PublicNavigationLink> Utility,
    IReadOnlyList<PublicNavigationLink> PublicSignal);

public sealed class PublicNavigationService
{
    private const string NavigationRelativePath = ".codex-design/product/PUBLIC_NAVIGATION.yaml";
    private readonly PublicCanonFileLoader _canon;
    private readonly PublicRouteCatalogService _routes;
    private readonly Lazy<PublicNavigationModel> _navigation;

    public PublicNavigationService(PublicCanonFileLoader canon, PublicRouteCatalogService routes)
    {
        _canon = canon;
        _routes = routes;
        _navigation = new Lazy<PublicNavigationModel>(BuildNavigation, LazyThreadSafetyMode.ExecutionAndPublication);
    }

    public PublicNavigationModel LoadNavigation() => _navigation.Value;

    private PublicNavigationModel BuildNavigation()
    {
        var document = _canon.LoadRequiredYaml<PublicNavigationDocument>(NavigationRelativePath);
        return new PublicNavigationModel(
            Primary: BuildLinks(document.PrimaryNav, "primary navigation"),
            Secondary: BuildLinks(document.SecondaryNav, "secondary navigation"),
            Utility: BuildLinks(document.UtilityNav, "utility navigation"),
            PublicSignal: BuildLinks(document.PublicSignalNav, "public signal navigation"));
    }

    private IReadOnlyList<PublicNavigationLink> BuildLinks(IReadOnlyList<PublicNavigationLinkDocument>? links, string group)
        => (links ?? new List<PublicNavigationLinkDocument>())
            .Select(link =>
            {
                if (string.IsNullOrWhiteSpace(link.Label))
                {
                    throw new InvalidOperationException($"{group} contains a link with a blank label.");
                }

                _routes.ValidateRouteTarget(link.Href, $"{group} link '{link.Label}'");
                return new PublicNavigationLink(link.Label, link.Href);
            })
            .ToArray();
}
