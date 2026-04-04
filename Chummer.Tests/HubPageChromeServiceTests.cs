using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class HubPageChromeServiceTests
{
    [Fact]
    public void BuildPublicChromeUsesGoogleStartForDownloadsHeaderSignIn()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var canon = new PublicCanonFileLoader(configuration);
        var routes = new PublicRouteCatalogService(canon);
        var service = new HubPageChromeService(
            new PublicLandingService(canon, new PublicActionResolver()),
            new PublicNavigationService(canon, routes),
            new PublicReleaseManifestService(configuration),
            new ReleaseSelectionService(canon));

        var chrome = service.BuildPublicChrome("Downloads", "Install the current preview.", "/downloads");

        var signIn = Assert.Single(chrome.HeaderActions, action => action.Label == "Sign in");
        Assert.Equal("/auth/google/start?next=%2Fdownloads", signIn.Href);
    }

    [Fact]
    public void BuildPublicChromeKeepsCanonicalSignInOnLoginRoute()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var canon = new PublicCanonFileLoader(configuration);
        var routes = new PublicRouteCatalogService(canon);
        var service = new HubPageChromeService(
            new PublicLandingService(canon, new PublicActionResolver()),
            new PublicNavigationService(canon, routes),
            new PublicReleaseManifestService(configuration),
            new ReleaseSelectionService(canon));

        var chrome = service.BuildPublicChrome("Sign in", "Continue into account surfaces.", "/login");

        var signIn = Assert.Single(chrome.HeaderActions, action => action.Label == "Sign in");
        Assert.Equal("/login?next=/home", signIn.Href);
    }

    [Fact]
    public void BuildPublicChromeKeepsCanonicalSignInOnAuthStartRoute()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var canon = new PublicCanonFileLoader(configuration);
        var routes = new PublicRouteCatalogService(canon);
        var service = new HubPageChromeService(
            new PublicLandingService(canon, new PublicActionResolver()),
            new PublicNavigationService(canon, routes),
            new PublicReleaseManifestService(configuration),
            new ReleaseSelectionService(canon));

        var chrome = service.BuildPublicChrome("Auth", "Provider handoff.", "/auth/google/start");

        var signIn = Assert.Single(chrome.HeaderActions, action => action.Label == "Sign in");
        Assert.Equal("/login?next=/home", signIn.Href);
    }
}
