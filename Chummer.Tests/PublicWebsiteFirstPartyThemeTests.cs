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
    public void ParticipateRouteStaysFirstPartyAndNormalizesToPartizipate()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));
        string appNavigation = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_NAVIGATION.yaml"));
        string participateView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml"));

        Assert.Contains("public IActionResult ParticipateAliasPage()", controller, StringComparison.Ordinal);
        Assert.Contains("public async Task<IActionResult> ParticipatePage(CancellationToken cancellationToken)", controller, StringComparison.Ordinal);
        Assert.Contains("=> RedirectPermanent(\"/partizipate\");", controller, StringComparison.Ordinal);
        Assert.Contains("private string? ResolveProductLiftHostedBoardHref()", controller, StringComparison.Ordinal);
        Assert.Contains("public IActionResult FeedbackPage()", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("https://chummer6.productlift.dev/", controller, StringComparison.Ordinal);
        Assert.Contains("var showBuildActionInHeader = !minimalSurface;", layout, StringComparison.Ordinal);
        Assert.Contains("!(minimalSurface && normalizeHeaderActionPath(action.Href).StartsWith(\"/downloads\"", layout, StringComparison.Ordinal);
        Assert.Contains("showBuildActionInHeader && buildAction is not null", layout, StringComparison.Ordinal);
        Assert.Contains("href: /partizipate", appNavigation, StringComparison.Ordinal);
        Assert.DoesNotContain("label: Get Chummer", appNavigation, StringComparison.Ordinal);
        Assert.DoesNotContain("productlift.dev", appNavigation, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("First-party route", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("Open in a tab", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("The board stays here. Open a separate tab only if your browser blocks the embed.", participateView, StringComparison.Ordinal);

        string siblingNavigationPath = Path.GetFullPath(Path.Combine(RepoPaths.Root, "..", "chummer-design", "products", "chummer", "PUBLIC_NAVIGATION.yaml"));
        if (!File.Exists(siblingNavigationPath))
        {
            return;
        }

        string siblingNavigation = File.ReadAllText(siblingNavigationPath);
        Assert.Contains("href: /partizipate", siblingNavigation, StringComparison.Ordinal);
        Assert.DoesNotContain("label: Get Chummer", siblingNavigation, StringComparison.Ordinal);
        Assert.DoesNotContain("productlift.dev", siblingNavigation, StringComparison.OrdinalIgnoreCase);
    }
}
