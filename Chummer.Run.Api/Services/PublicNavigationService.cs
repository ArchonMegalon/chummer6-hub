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

    public PublicNavigationService(PublicCanonFileLoader canon)
    {
        _canon = canon;
    }

    public PublicNavigationModel LoadNavigation()
    {
        var document = _canon.LoadRequiredYaml<PublicNavigationDocument>(NavigationRelativePath);
        return new PublicNavigationModel(
            Primary: (document.PrimaryNav ?? new List<PublicNavigationLinkDocument>())
                .Select(static link => new PublicNavigationLink(link.Label, link.Href))
                .ToArray(),
            Secondary: (document.SecondaryNav ?? new List<PublicNavigationLinkDocument>())
                .Select(static link => new PublicNavigationLink(link.Label, link.Href))
                .ToArray(),
            Utility: (document.UtilityNav ?? new List<PublicNavigationLinkDocument>())
                .Select(static link => new PublicNavigationLink(link.Label, link.Href))
                .ToArray());
    }
}
