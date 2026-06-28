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
        string participateView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Partizipate.cshtml"));
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));
        string appNavigation = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_NAVIGATION.yaml"));

        Assert.Contains("public async Task<IActionResult> ParticipateAliasPage(CancellationToken cancellationToken)", controller, StringComparison.Ordinal);
        Assert.Contains("public async Task<IActionResult> ParticipatePage(CancellationToken cancellationToken)", controller, StringComparison.Ordinal);
        Assert.Contains("return Redirect($\"/participate{Request.QueryString}\");", controller, StringComparison.Ordinal);
        Assert.Contains("BuildFirstPartyParticipateBoardAsync", controller, StringComparison.Ordinal);
        Assert.Contains("\"~/Views/PublicLanding/Partizipate.cshtml\"", controller, StringComparison.Ordinal);
        Assert.Contains("private static string BuildParticipateFrameHref(", controller, StringComparison.Ordinal);
        Assert.Contains("BuildParticipateBoardRouteHref(normalizedBoardPath)", controller, StringComparison.Ordinal);
        Assert.Contains("public IActionResult ParticipateBoardFrame(string? boardPath)", controller, StringComparison.Ordinal);
        Assert.Contains("public IActionResult FeedbackPage()", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("https://chummer6.productlift.dev/", controller, StringComparison.Ordinal);
        Assert.Contains("!(minimalSurface && normalizeHeaderActionPath(action.Href).StartsWith(\"/downloads\"", layout, StringComparison.Ordinal);
        Assert.Contains("var showPrimaryNavInHeader = !minimalSurface && routeKey is not \"landing\";", layout, StringComparison.Ordinal);
        Assert.Contains("accountMenuBuildAction = chrome.Authenticated ? buildAction : null", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("launcherDesktopLabel", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("launcherWebLabel", layout, StringComparison.Ordinal);
        Assert.Contains("href: /participate", appNavigation, StringComparison.Ordinal);
        Assert.DoesNotContain("href: /mobile", appNavigation, StringComparison.Ordinal);
        Assert.DoesNotContain("label: Get Chummer", appNavigation, StringComparison.Ordinal);
        Assert.DoesNotContain("productlift.dev", appNavigation, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("data-chummer-participate-frame", participateView, StringComparison.Ordinal);
        Assert.Contains("@PublicParticipateText(Model.Summary)", participateView, StringComparison.Ordinal);
        Assert.Contains("Current requests", participateView, StringComparison.Ordinal);
        Assert.Contains("Board is live.", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("Feedback and roadmap live here.", participateView, StringComparison.Ordinal);
        Assert.Contains("Model.EmbeddedBoardHref", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("data-chummer-board-skin", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("#2e7bff", controller, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("#39c6ff", controller, StringComparison.OrdinalIgnoreCase);

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

        Assert.Contains("public async Task<IActionResult> RoadmapPage(CancellationToken cancellationToken)", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/roadmap/board\")]", controller, StringComparison.Ordinal);
        Assert.Contains("\"~/Views/PublicLanding/Roadmap.cshtml\"", controller, StringComparison.Ordinal);
        Assert.Contains("return Redirect($\"/roadmap{Request.QueryString}\");", controller, StringComparison.Ordinal);
        Assert.Contains("pageTitle: \"Roadmap - Chummer.run\"", controller, StringComparison.Ordinal);
        Assert.Contains("hostedHeadingReplacement: \"In progress.\"", controller, StringComparison.Ordinal);
        Assert.Contains("HostedBoardHtmlLooksUnavailable(html)", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("https://chummer6.productlift.dev/", controller, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("BuildRoadmapFallbackPageModelAsync", controller, StringComparison.Ordinal);
        Assert.Contains("RoadmapBoardFallbackAsync", controller, StringComparison.Ordinal);
        Assert.Contains("data-chummer-roadmap-frame", roadmapView, StringComparison.Ordinal);
        Assert.Contains("Work opens below.", roadmapView, StringComparison.Ordinal);
    }

    [Fact]
    public void SoftwareApplicationSchemaDoesNotHardCodeUnavailablePlatforms()
    {
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));

        Assert.DoesNotContain("[\"operatingSystem\"] = \"Windows, Linux\"", layout, StringComparison.Ordinal);
        Assert.Contains("SoftwareApplicationOperatingSystem", layout, StringComparison.Ordinal);
        Assert.Contains("softwareApplicationOperatingSystem = \"Linux\"", layout, StringComparison.Ordinal);
    }

    [Fact]
    public void LayoutKeepsAbsoluteSocialUrlOnNoIndexRoutes()
    {
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));

        Assert.Contains("var absoluteRequestUrl = string.IsNullOrWhiteSpace(resolvedRequestHost)", layout, StringComparison.Ordinal);
        Assert.Contains("var socialUrl = string.IsNullOrWhiteSpace(canonicalUrl) ? absoluteRequestUrl : canonicalUrl;", layout, StringComparison.Ordinal);
        Assert.Contains("<meta property=\"og:url\" content=\"@socialUrl\" />", layout, StringComparison.Ordinal);
        Assert.Contains("<meta name=\"twitter:url\" content=\"@socialUrl\" />", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("<meta property=\"og:url\" content=\"@canonicalUrl\" />", layout, StringComparison.Ordinal);
    }
}
