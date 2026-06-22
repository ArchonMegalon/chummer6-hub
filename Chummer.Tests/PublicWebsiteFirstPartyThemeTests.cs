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
    public void ParticipatePageIsFirstPartyAndDoesNotExposeProviderBranding()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml"));

        Assert.Contains("return View(\"~/Views/PublicLanding/Participate.cshtml\", model);", controller, StringComparison.Ordinal);
        Assert.Contains("public IActionResult FeedbackPage()", controller, StringComparison.Ordinal);
        Assert.Contains("=> Redirect(\"/participate\");", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("DefaultProductLiftFeedbackUrl", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("ExternalBoardUrl", controller, StringComparison.Ordinal);
        Assert.Contains("First-party page", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Made with", view, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("ProductLift", view, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("productlift.dev", view, StringComparison.OrdinalIgnoreCase);
    }
}
