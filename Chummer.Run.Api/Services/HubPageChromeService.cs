using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api.Services;

public sealed class HubPageChromeService
{
    private readonly PublicLandingService _landing;
    private readonly PublicNavigationService _navigation;
    private readonly PublicReleaseManifestService _releases;
    private readonly ReleaseSelectionService _releaseSelection;
    private readonly IHttpContextAccessor _httpContextAccessor;

    public HubPageChromeService(
        PublicLandingService landing,
        PublicNavigationService navigation,
        PublicReleaseManifestService releases,
        ReleaseSelectionService releaseSelection,
        IHttpContextAccessor httpContextAccessor)
    {
        _landing = landing;
        _navigation = navigation;
        _releases = releases;
        _releaseSelection = releaseSelection;
        _httpContextAccessor = httpContextAccessor;
    }

    public SiteChromeViewModel BuildPublicChrome(string title, string description, string currentPath)
    {
        var surface = _landing.LoadSurface();
        var nav = _navigation.LoadNavigation();
        var normalizedCurrentPath = NormalizeRoute(currentPath);
        var downloadsSurface = normalizedCurrentPath.StartsWith("/downloads", StringComparison.OrdinalIgnoreCase);
        var publicPrimaryCta = downloadsSurface ? null : ResolvePublicPrimaryCta(surface, currentPath);
        var heroPrimaryAction = surface.HeroCtas
            .FirstOrDefault(action => string.Equals(action.Emphasis, "primary", StringComparison.OrdinalIgnoreCase));
        var signInAction = surface.GuestShellActions
            .FirstOrDefault(action => string.Equals(NormalizeRoute(action.Href), "/login", StringComparison.OrdinalIgnoreCase))
            ?? new PublicLandingActionDto("Sign in", "/login?next=/home", "secondary");
        var createAccountAction = surface.GuestShellActions
            .FirstOrDefault(action => string.Equals(NormalizeRoute(action.Href), "/signup", StringComparison.OrdinalIgnoreCase))
            ?? new PublicLandingActionDto("Claim your copy", "/signup?next=/home", "primary");
        var contextualSignInHref = BuildContextualSignInHref(normalizedCurrentPath, signInAction.Href);
        var primaryHeaderAction = downloadsSurface
            ? null
            : string.Equals(NormalizeRoute(currentPath), "/", StringComparison.OrdinalIgnoreCase) && heroPrimaryAction is not null
            ? heroPrimaryAction
            : publicPrimaryCta is null
            ? createAccountAction
            : new PublicLandingActionDto(publicPrimaryCta.Label, publicPrimaryCta.Href, publicPrimaryCta.Emphasis);
        var actions = new List<SiteChromeActionViewModel>
        {
            new(
                signInAction.Label,
                contextualSignInHref,
                "link",
                Current: string.Equals(normalizedCurrentPath, NormalizeRoute(contextualSignInHref), StringComparison.OrdinalIgnoreCase))
        };

        if (primaryHeaderAction is not null)
        {
            actions.Add(new SiteChromeActionViewModel(
                primaryHeaderAction.Label,
                primaryHeaderAction.Href,
                primaryHeaderAction.Emphasis,
                Current: string.Equals(normalizedCurrentPath, NormalizeRoute(primaryHeaderAction.Href), StringComparison.OrdinalIgnoreCase)));
        }

        var publicPrimaryCtaView = publicPrimaryCta is null
            ? null
            : new SiteChromeActionViewModel(publicPrimaryCta.Label, publicPrimaryCta.Href, publicPrimaryCta.Emphasis);

        return new SiteChromeViewModel(
            Title: PublicFacingCopyHumanizer.Clean(title),
            Description: PublicFacingCopyHumanizer.Clean(description),
            CurrentPath: currentPath,
            PrimaryNavigation: nav.Primary,
            SecondaryNavigation: nav.Secondary,
            UtilityNavigation: nav.Utility,
            HeaderActions: actions.ToArray(),
            PublicPrimaryCta: publicPrimaryCtaView,
            Authenticated: false,
            SignedInLabel: null,
            FooterCanonicalSource: surface.FooterCanonicalSource,
            FooterGeneratedNote: surface.FooterGeneratedNote,
            PublicSignalNavigation: nav.PublicSignal);
    }

    private static string BuildContextualSignInHref(string normalizedCurrentPath, string fallbackHref)
    {
        if (normalizedCurrentPath.StartsWith("/downloads", StringComparison.OrdinalIgnoreCase)
            || normalizedCurrentPath.StartsWith("/participate", StringComparison.OrdinalIgnoreCase))
        {
            return $"/auth/google/start?next={Uri.EscapeDataString(normalizedCurrentPath)}";
        }

        if (normalizedCurrentPath.StartsWith("/login", StringComparison.OrdinalIgnoreCase)
            || normalizedCurrentPath.StartsWith("/signup", StringComparison.OrdinalIgnoreCase)
            || normalizedCurrentPath.StartsWith("/auth/", StringComparison.OrdinalIgnoreCase))
        {
            return string.IsNullOrWhiteSpace(fallbackHref) ? "/login" : fallbackHref.Trim();
        }

        return $"/login?next={Uri.EscapeDataString(normalizedCurrentPath)}";
    }

    public SiteChromeViewModel BuildAuthenticatedChrome(
        string title,
        string description,
        string currentPath,
        string signedInLabel,
        string? signedInEmail = null)
    {
        var surface = _landing.LoadSurface();
        var nav = _navigation.LoadNavigation();
        var normalizedCurrentPath = NormalizeRoute(currentPath);
        var actions = new List<SiteChromeActionViewModel>
        {
            new SiteChromeActionViewModel("Home", "/home", "secondary", normalizedCurrentPath.StartsWith("/home", StringComparison.OrdinalIgnoreCase))
        };

        if (ReleaseUploadAccessPolicy.CanAccess(signedInEmail))
        {
            actions.Add(new SiteChromeActionViewModel(
                "Build",
                "/downloads/release-upload",
                "secondary",
                normalizedCurrentPath.StartsWith("/downloads/release-upload", StringComparison.OrdinalIgnoreCase)));
        }

        actions.AddRange(
        [
            new SiteChromeActionViewModel("Account", "/account", "secondary", normalizedCurrentPath.StartsWith("/account", StringComparison.OrdinalIgnoreCase)),
            new SiteChromeActionViewModel("Sign out", "/logout", "primary")
        ]);

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
            FooterGeneratedNote: surface.FooterGeneratedNote,
            PublicSignalNavigation: nav.PublicSignal);
    }

    private PublicLandingActionDto BuildPublicPrimaryCta()
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var userAgent = _httpContextAccessor.HttpContext?.Request.Headers.UserAgent.ToString() ?? string.Empty;
        var action = _releaseSelection.BuildPublicPrimaryAction(manifest, userAgent, authenticated: false);
        return new PublicLandingActionDto(action.Label, action.Href, action.Emphasis);
    }

    private PublicLandingActionDto ResolvePublicPrimaryCta(PublicLandingSurfaceDto surface, string currentPath)
    {
        var releaseCta = BuildPublicPrimaryCta();
        if (!string.Equals(NormalizeRoute(currentPath), "/", StringComparison.OrdinalIgnoreCase))
        {
            return releaseCta;
        }

        return surface.HeroCtas
            .FirstOrDefault(action => string.Equals(action.Emphasis, "primary", StringComparison.OrdinalIgnoreCase))
            ?? surface.HeroCtas.FirstOrDefault()
            ?? releaseCta;
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
