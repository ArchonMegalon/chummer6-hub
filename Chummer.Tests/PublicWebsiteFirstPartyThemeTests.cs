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
        Assert.Contains("__CHUMMER_HEADING_REPLACEMENT__", controller, StringComparison.Ordinal);
        Assert.Contains("hiddenStatusTerms", controller, StringComparison.Ordinal);
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

        Assert.Contains("public async Task<IActionResult> RoadmapPage(CancellationToken cancellationToken)", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/roadmap/board\")]", controller, StringComparison.Ordinal);
        Assert.Contains("RoadmapBoardProxyCore(", controller, StringComparison.Ordinal);
        Assert.Contains("canonicalHref: \"/roadmap\"", controller, StringComparison.Ordinal);
        Assert.Contains("assetProxyBasePath: \"/roadmap/provider-assets\"", controller, StringComparison.Ordinal);
        Assert.Contains("pageTitle: \"Roadmap - Chummer.run\"", controller, StringComparison.Ordinal);
        Assert.Contains("HostedBoardHtmlLooksUnavailable(html)", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("https://chummer6.productlift.dev/", controller, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("return View(\"~/Views/PublicLanding/Roadmap.cshtml\", model);", controller, StringComparison.Ordinal);
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
