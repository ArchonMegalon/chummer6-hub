using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class HubPageChromeService
{
    private readonly PublicLandingService _landing;
    private readonly PublicNavigationService _navigation;
    private readonly PublicReleaseManifestService _releases;
    private readonly ReleaseSelectionService _releaseSelection;

    public HubPageChromeService(
        PublicLandingService landing,
        PublicNavigationService navigation,
        PublicReleaseManifestService releases,
        ReleaseSelectionService releaseSelection)
    {
        _landing = landing;
        _navigation = navigation;
        _releases = releases;
        _releaseSelection = releaseSelection;
    }

    public SiteChromeViewModel BuildPublicChrome(string title, string description, string currentPath)
    {
        var surface = _landing.LoadSurface();
        var nav = _navigation.LoadNavigation();
        var publicPrimaryCta = BuildPublicPrimaryCta();
        var signInAction = surface.GuestShellActions
            .FirstOrDefault(action => string.Equals(NormalizeRoute(action.Href), "/login", StringComparison.OrdinalIgnoreCase))
            ?? new PublicLandingActionDto("Sign in", "/login?next=/home", "secondary");
        var createAccountAction = surface.GuestShellActions
            .FirstOrDefault(action => string.Equals(NormalizeRoute(action.Href), "/signup", StringComparison.OrdinalIgnoreCase))
            ?? new PublicLandingActionDto("Create account", "/signup?next=/home", "primary");
        var primaryHeaderAction = publicPrimaryCta is null
            ? createAccountAction
            : new PublicLandingActionDto(publicPrimaryCta.Label, publicPrimaryCta.Href, publicPrimaryCta.Tone);
        var actions = new[]
        {
            new SiteChromeActionViewModel(
                signInAction.Label,
                signInAction.Href,
                "link",
                Current: string.Equals(NormalizeRoute(currentPath), NormalizeRoute(signInAction.Href), StringComparison.OrdinalIgnoreCase)),
            new SiteChromeActionViewModel(
                primaryHeaderAction.Label,
                primaryHeaderAction.Href,
                primaryHeaderAction.Emphasis,
                Current: string.Equals(NormalizeRoute(currentPath), NormalizeRoute(primaryHeaderAction.Href), StringComparison.OrdinalIgnoreCase))
        };

        return new SiteChromeViewModel(
            Title: title,
            Description: description,
            CurrentPath: currentPath,
            PrimaryNavigation: nav.Primary,
            SecondaryNavigation: nav.Secondary,
            UtilityNavigation: nav.Utility,
            HeaderActions: actions,
            PublicPrimaryCta: publicPrimaryCta,
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
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var action = _releaseSelection.BuildPublicPrimaryAction(manifest, authenticated: false);
        return new SiteChromeActionViewModel(action.Label, action.Href, action.Emphasis);
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
