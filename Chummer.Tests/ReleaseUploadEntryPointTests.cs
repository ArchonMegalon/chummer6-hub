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
        Assert.Contains("ReleaseUploadAccessPolicy.CanAccess(ResolveReleaseUploadAccessEmail(signedInLabel, signedInEmail))", chromeService, StringComparison.Ordinal);
        Assert.DoesNotContain("chrome.Authenticated && !hasBuildAction", layout, StringComparison.Ordinal);
    }

    [Fact]
    public void ReleaseUploadRouteUsesInlineNavigationWithoutStoredDrawerPreference()
    {
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));
        string script = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "js", "site.js"));
        string css = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "css", "site.css"));

        Assert.Contains("<nav class=\"site-nav\" aria-label=\"Primary navigation\">", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("var defaultNavOpen", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("route-downloads-release-upload", script, StringComparison.Ordinal);
        Assert.DoesNotContain("forceDesktopNavCollapsed", script, StringComparison.Ordinal);
        Assert.DoesNotContain("closeNavPanel();", script, StringComparison.Ordinal);
        Assert.DoesNotContain("nav-panel-open", css, StringComparison.Ordinal);
        Assert.DoesNotContain("site-sidebar", css, StringComparison.Ordinal);
    }

    [Fact]
    public void AuthenticatedHeaderUsesAccountDropdownForReleaseUploadAccess()
    {
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));

        Assert.Contains("if (chrome.Authenticated)", layout, StringComparison.Ordinal);
        Assert.Contains("<details class=\"site-account-menu\">", layout, StringComparison.Ordinal);
        Assert.Contains("var accountMenuBuildAction = chrome.Authenticated ? buildAction : null;", layout, StringComparison.Ordinal);
        Assert.Contains("@if (accountMenuBuildAction is not null)", layout, StringComparison.Ordinal);
        Assert.Contains("<a class=\"site-account-menu__link\" href=\"@accountMenuBuildAction.Href\">@accountMenuBuildAction.Label</a>", layout, StringComparison.Ordinal);
        Assert.Contains("@foreach (var action in accountMenuActions)", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("<a class=\"site-actions__link\" href=\"@buildAction.Href\">@buildAction.Label</a>", layout, StringComparison.Ordinal);
    }
}
