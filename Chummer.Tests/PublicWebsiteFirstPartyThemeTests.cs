using System;
using System.IO;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicWebsiteFirstPartyThemeTests
{
    [Fact]
    public void PublicThemeDoesNotReintroduceElectricBlueAccentPalette()
    {
        string css = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "css", "site.css"));

        Assert.DoesNotContain("#78ddff", css, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("#2e7bff", css, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("#39c6ff", css, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("#8bc7ff", css, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("rgba(57, 198, 255", css, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("rgba(46, 123, 255", css, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ParticipateRouteAndLegacyTypoStayFirstParty()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));
        string appNavigation = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_NAVIGATION.yaml"));

        Assert.Contains("public async Task<IActionResult> ParticipateAliasPage(CancellationToken cancellationToken)", controller, StringComparison.Ordinal);
        Assert.Contains("public async Task<IActionResult> ParticipatePage(CancellationToken cancellationToken)", controller, StringComparison.Ordinal);
        Assert.Contains("return Redirect($\"/participate{Request.QueryString}\");", controller, StringComparison.Ordinal);
        Assert.Contains("BuildFirstPartyParticipateBoardAsync", controller, StringComparison.Ordinal);
        Assert.Contains("ParticipateBoardProxyCore(", controller, StringComparison.Ordinal);
        Assert.Contains("localOrigin: \"/participate\"", controller, StringComparison.Ordinal);
        Assert.Contains("private string? ResolveProductLiftHostedBoardHref()", controller, StringComparison.Ordinal);
        Assert.Contains("public IActionResult FeedbackPage()", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("https://chummer6.productlift.dev/", controller, StringComparison.Ordinal);
        Assert.Contains("var showBuildActionInHeader = !minimalSurface;", layout, StringComparison.Ordinal);
        Assert.Contains("!(minimalSurface && normalizeHeaderActionPath(action.Href).StartsWith(\"/downloads\"", layout, StringComparison.Ordinal);
        Assert.Contains("showBuildActionInHeader && buildAction is not null", layout, StringComparison.Ordinal);
        Assert.Contains("href: /participate", appNavigation, StringComparison.Ordinal);
        Assert.DoesNotContain("label: Get Chummer", appNavigation, StringComparison.Ordinal);
        Assert.DoesNotContain("productlift.dev", appNavigation, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("body > header,", controller, StringComparison.Ordinal);
        Assert.Contains("[id*=\"global-search\"]", controller, StringComparison.Ordinal);
        Assert.Contains("new RegExp('\\\\bWhat do you want' + ' to see next\\\\?'", controller, StringComparison.Ordinal);
        Assert.Contains("text === 'search' || text === 'ctrl k'", controller, StringComparison.Ordinal);
        Assert.Contains("data-chummer-board-skin", controller, StringComparison.Ordinal);
        Assert.Contains("RemoveHostedBoardAuthLinks", controller, StringComparison.Ordinal);

        string siblingNavigationPath = Path.GetFullPath(Path.Combine(RepoPaths.Root, "..", "chummer-design", "products", "chummer", "PUBLIC_NAVIGATION.yaml"));
        if (!File.Exists(siblingNavigationPath))
        {
            return;
        }

        string siblingNavigation = File.ReadAllText(siblingNavigationPath);
        Assert.Contains("href: /participate", siblingNavigation, StringComparison.Ordinal);
        Assert.DoesNotContain("label: Get Chummer", siblingNavigation, StringComparison.Ordinal);
        Assert.DoesNotContain("productlift.dev", siblingNavigation, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RoadmapRouteRendersProductLiftRequestsAsFirstPartyData()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string roadmapView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Roadmap.cshtml"));

        Assert.Contains("TryFetchFirstPartyParticipatePostsAsync", controller, StringComparison.Ordinal);
        Assert.Contains("PublicRequests: publicRequests.Posts.Take(3).ToArray()", controller, StringComparison.Ordinal);
        Assert.Contains("PublicRequestCount: publicRequests.TotalCount", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/roadmap/board\")]", controller, StringComparison.Ordinal);
        Assert.Contains("RoadmapBoardProxy", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("https://chummer6.productlift.dev/", controller, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Model.PublicRequests.Count > 0", roadmapView, StringComparison.Ordinal);
        Assert.Contains("What people ask for", roadmapView, StringComparison.Ordinal);
        Assert.Contains("Model.PublicRequestCount public requests", roadmapView, StringComparison.Ordinal);
        Assert.Contains("id=\"roadmap-board\"", roadmapView, StringComparison.Ordinal);
        Assert.Contains("<iframe", roadmapView, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Roadmap guidance", roadmapView, StringComparison.Ordinal);
        Assert.DoesNotContain("Quick links", roadmapView, StringComparison.Ordinal);
        Assert.DoesNotContain("planning surface", roadmapView, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Use the right place", roadmapView, StringComparison.Ordinal);
    }

    [Fact]
    public void SoftwareApplicationSchemaDoesNotHardCodeUnavailablePlatforms()
    {
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));

        Assert.DoesNotContain("[\"operatingSystem\"] = \"Windows, Linux\"", layout, StringComparison.Ordinal);
        Assert.Contains("SoftwareApplicationOperatingSystem", layout, StringComparison.Ordinal);
        Assert.Contains("softwareApplicationOperatingSystem = \"Linux\"", layout, StringComparison.Ordinal);
    }
}
