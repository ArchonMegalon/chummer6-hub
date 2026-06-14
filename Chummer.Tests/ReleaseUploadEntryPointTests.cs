using System;
using System.IO;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseUploadEntryPointTests
{
    [Fact]
    public void ReleaseUploadSurfaceIsScopedToTheConfiguredOwner()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string chromeService = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Services", "HubPageChromeService.cs"));
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));

        Assert.Contains("ReleaseUploadAccessPolicy.CanAccess(subject.Email)", controller, StringComparison.Ordinal);
        Assert.Contains("return NotFound();", controller, StringComparison.Ordinal);
        Assert.Contains("ReleaseUploadAccessPolicy.CanAccess(signedInEmail)", chromeService, StringComparison.Ordinal);
        Assert.DoesNotContain("chrome.Authenticated && !hasBuildAction", layout, StringComparison.Ordinal);
    }

    [Fact]
    public void ReleaseUploadRouteStartsWithNavigationCollapsedAndSkipsStoredDesktopNavPreference()
    {
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));
        string script = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "js", "site.js"));
        string css = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "css", "site.css"));

        Assert.Contains("var defaultNavOpen = false;", layout, StringComparison.Ordinal);
        Assert.Contains("route-downloads-release-upload", script, StringComparison.Ordinal);
        Assert.Contains("if (forceDesktopNavCollapsed)", script, StringComparison.Ordinal);
        Assert.Contains("closeNavPanel();", script, StringComparison.Ordinal);
        Assert.Contains(".shell-authenticated:not(.nav-panel-open) .site-sidebar", css, StringComparison.Ordinal);
        Assert.Contains(".shell-authenticated.nav-panel-open .site-sidebar", css, StringComparison.Ordinal);
    }
}
