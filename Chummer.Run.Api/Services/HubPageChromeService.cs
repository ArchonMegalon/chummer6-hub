using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class HubPageChromeService
{
    private readonly PublicLandingService _landing;
    private readonly PublicNavigationService _navigation;
    private readonly PublicReleaseManifestService _releases;

    public HubPageChromeService(PublicLandingService landing, PublicNavigationService navigation, PublicReleaseManifestService releases)
    {
        _landing = landing;
        _navigation = navigation;
        _releases = releases;
    }

    public SiteChromeViewModel BuildPublicChrome(string title, string description, string currentPath)
    {
        var surface = _landing.LoadSurface();
        var nav = _navigation.LoadNavigation();
        var signInAction = surface.GuestShellActions
            .FirstOrDefault(action => string.Equals(NormalizeRoute(action.Href), "/login", StringComparison.OrdinalIgnoreCase))
            ?? new PublicLandingActionDto("Sign in", "/login?next=/home", "secondary");
        var createAccountAction = surface.GuestShellActions
            .FirstOrDefault(action => string.Equals(NormalizeRoute(action.Href), "/signup", StringComparison.OrdinalIgnoreCase))
            ?? new PublicLandingActionDto("Create account", "/signup?next=/home", "primary");
        var actions = new[]
        {
            new SiteChromeActionViewModel(
                signInAction.Label,
                signInAction.Href,
                "link",
                Current: string.Equals(NormalizeRoute(currentPath), NormalizeRoute(signInAction.Href), StringComparison.OrdinalIgnoreCase)),
            new SiteChromeActionViewModel(
                createAccountAction.Label,
                createAccountAction.Href,
                createAccountAction.Emphasis,
                Current: string.Equals(NormalizeRoute(currentPath), NormalizeRoute(createAccountAction.Href), StringComparison.OrdinalIgnoreCase))
        };

        return new SiteChromeViewModel(
            Title: title,
            Description: description,
            CurrentPath: currentPath,
            PrimaryNavigation: nav.Primary,
            SecondaryNavigation: nav.Secondary,
            UtilityNavigation: nav.Utility,
            HeaderActions: actions,
            PublicPrimaryCta: BuildPublicPrimaryCta(),
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
            UtilityNavigation: nav.Utility,
            HeaderActions: actions,
            PublicPrimaryCta: null,
            Authenticated: true,
            SignedInLabel: signedInLabel,
            FooterCanonicalSource: surface.FooterCanonicalSource,
            FooterGeneratedNote: surface.FooterGeneratedNote);
    }

    private SiteChromeActionViewModel BuildPublicPrimaryCta()
    {
        var manifest = _releases.LoadManifest();
        var hasPreviewBuild = manifest.Downloads.Count > 0;
        return hasPreviewBuild
            ? new SiteChromeActionViewModel("Get preview build", "/downloads", "primary")
            : new SiteChromeActionViewModel("Request early access", "/signup?next=/home", "primary");
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
