using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class HubPageChromeService
{
    private readonly PublicLandingService _landing;
    private readonly PublicNavigationService _navigation;

    public HubPageChromeService(PublicLandingService landing, PublicNavigationService navigation)
    {
        _landing = landing;
        _navigation = navigation;
    }

    public SiteChromeViewModel BuildPublicChrome(string title, string description, string currentPath)
    {
        var surface = _landing.LoadSurface();
        var nav = _navigation.LoadNavigation();
        var actions = surface.GuestShellActions
            .Select(action => new SiteChromeActionViewModel(
                action.Label,
                action.Href,
                action.Emphasis,
                Current: string.Equals(NormalizeRoute(currentPath), NormalizeRoute(action.Href), StringComparison.OrdinalIgnoreCase)))
            .ToArray();

        return new SiteChromeViewModel(
            Title: title,
            Description: description,
            CurrentPath: currentPath,
            PrimaryNavigation: nav.Primary,
            SecondaryNavigation: nav.Secondary,
            HeaderActions: actions,
            Authenticated: false,
            SignedInLabel: null,
            FooterCanonicalSource: surface.FooterCanonicalSource,
            FooterGeneratedNote: surface.FooterGeneratedNote);
    }

    public SiteChromeViewModel BuildAuthenticatedChrome(string title, string description, string currentPath, string signedInLabel)
    {
        var surface = _landing.LoadSurface();
        var nav = _navigation.LoadNavigation();
        var actions = new[]
        {
            new SiteChromeActionViewModel("Home", "/home", "secondary", string.Equals(currentPath, "/home", StringComparison.OrdinalIgnoreCase)),
            new SiteChromeActionViewModel("Account", "/account", "secondary", string.Equals(currentPath, "/account", StringComparison.OrdinalIgnoreCase)),
            new SiteChromeActionViewModel("Sign out", "/logout", "primary")
        };

        return new SiteChromeViewModel(
            Title: title,
            Description: description,
            CurrentPath: currentPath,
            PrimaryNavigation: nav.Primary,
            SecondaryNavigation: nav.Secondary,
            HeaderActions: actions,
            Authenticated: true,
            SignedInLabel: signedInLabel,
            FooterCanonicalSource: surface.FooterCanonicalSource,
            FooterGeneratedNote: surface.FooterGeneratedNote);
    }

    private static string NormalizeRoute(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return "/";
        }

        var trimmed = value.Trim();
        var query = trimmed.IndexOf('?');
        if (query >= 0)
        {
            trimmed = trimmed[..query];
        }

        return string.IsNullOrWhiteSpace(trimmed) ? "/" : trimmed;
    }
}
