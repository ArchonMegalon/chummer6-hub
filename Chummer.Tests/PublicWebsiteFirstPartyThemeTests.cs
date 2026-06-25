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
        string participateView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml"));

        Assert.Contains("public async Task<IActionResult> ParticipateAliasPage(CancellationToken cancellationToken)", controller, StringComparison.Ordinal);
        Assert.Contains("public async Task<IActionResult> ParticipatePage(CancellationToken cancellationToken)", controller, StringComparison.Ordinal);
        Assert.Contains("return await ParticipateBoardProxyCore(string.Empty, cancellationToken).ConfigureAwait(false);", controller, StringComparison.Ordinal);
        Assert.Contains("private string? ResolveProductLiftHostedBoardHref()", controller, StringComparison.Ordinal);
        Assert.Contains("public IActionResult FeedbackPage()", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("https://chummer6.productlift.dev/", controller, StringComparison.Ordinal);
        Assert.Contains("var showBuildActionInHeader = !minimalSurface;", layout, StringComparison.Ordinal);
        Assert.Contains("!(minimalSurface && normalizeHeaderActionPath(action.Href).StartsWith(\"/downloads\"", layout, StringComparison.Ordinal);
        Assert.Contains("showBuildActionInHeader && buildAction is not null", layout, StringComparison.Ordinal);
        Assert.Contains("href: /participate", appNavigation, StringComparison.Ordinal);
        Assert.DoesNotContain("label: Get Chummer", appNavigation, StringComparison.Ordinal);
        Assert.DoesNotContain("productlift.dev", appNavigation, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Requests, votes, and shipped work.", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("Support Chummer", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("Open in a tab", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("The board stays here. Open a separate tab only if your browser blocks the embed.", participateView, StringComparison.Ordinal);
        Assert.Contains("data-participate-board-fallback", participateView, StringComparison.Ordinal);
        Assert.Contains("['sup' + 'port', 'pro' + 'duct' + 'lift.dev'].join(String.fromCharCode(64))", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("support@productlift.dev", participateView, StringComparison.OrdinalIgnoreCase);

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
    public void RoadmapRouteCanUseHostedProductLiftBoardWithoutLeavingFirstPartyChrome()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string roadmapView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Roadmap.cshtml"));

        Assert.Contains("ResolveProductLiftHostedRoadmapHref()", controller, StringComparison.Ordinal);
        Assert.Contains("ResolveProductLiftHostedRoadmapUri()", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/roadmap/board\")]", controller, StringComparison.Ordinal);
        Assert.Contains("RoadmapBoardProxy", controller, StringComparison.Ordinal);
        Assert.Contains("Chummer Roadmap", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("https://chummer6.productlift.dev/", controller, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("@if (!string.IsNullOrWhiteSpace(Model.HostedBoardHref))", roadmapView, StringComparison.Ordinal);
        Assert.Contains("id=\"roadmap-board\"", roadmapView, StringComparison.Ordinal);
        Assert.Contains("src=\"@Model.HostedBoardHref\"", roadmapView, StringComparison.Ordinal);
        Assert.Contains("What is moving next.", roadmapView, StringComparison.Ordinal);
        Assert.Contains("Planned work, visible here.", roadmapView, StringComparison.Ordinal);
        Assert.DoesNotContain("planning surface", roadmapView, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Use the right place", roadmapView, StringComparison.Ordinal);
    }

    [Fact]
    public void SoftwareApplicationSchemaDoesNotHardCodeUnavailablePlatforms()
    {
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));
        string downloadsView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml"));

        Assert.DoesNotContain("[\"operatingSystem\"] = \"Windows, Linux\"", layout, StringComparison.Ordinal);
        Assert.Contains("SoftwareApplicationOperatingSystem", layout, StringComparison.Ordinal);
        Assert.Contains("SoftwareApplicationOperatingSystem", downloadsView, StringComparison.Ordinal);
        Assert.Contains("string.Join(\", \", promotedPlatformLabels)", downloadsView, StringComparison.Ordinal);
    }
}
