using Xunit;

namespace Chummer.Tests;

public sealed class SupportSubmittedFlagshipViewTests
{
    [Fact]
    public void SupportSubmittedPageUsesARoutePackAndResponseHelperPack()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "SupportSubmitted.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("ViewData[\"SurfaceClass\"] = \"surface-support-submitted surface-minimal\";", view, StringComparison.Ordinal);
        Assert.Contains("Choose the next step.", view, StringComparison.Ordinal);
        Assert.Contains("Case details", view, StringComparison.Ordinal);
        Assert.Contains("Keep the case handy.", view, StringComparison.Ordinal);
        Assert.Contains("This page keeps the current case status", view, StringComparison.Ordinal);
        Assert.Contains("Open current release", view, StringComparison.Ordinal);
        Assert.Contains("Same recovery path", view, StringComparison.Ordinal);
        Assert.Contains("PublicSupportSubmittedText(fact.Summary)", view, StringComparison.Ordinal);
        Assert.Contains("PublicSupportSubmittedText(Model.Heading)", view, StringComparison.Ordinal);
        Assert.Contains("PublicSupportSubmittedText(route.Label)", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Follow-up status", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Fix status", view, StringComparison.Ordinal);
        Assert.DoesNotContain("This pack", view, StringComparison.Ordinal);
    }

    [Fact]
    public void SupportSubmittedPageKeepsTimelineAndSavedEvidenceAsDrawers()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "SupportSubmitted.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Case timeline", view, StringComparison.Ordinal);
        Assert.Contains("Model.TrackedCaseSummary?.TimelineHighlights is { Count: > 0 }", view, StringComparison.Ordinal);
        Assert.Contains("Saved files", view, StringComparison.Ordinal);
        Assert.DoesNotContain("_SignedInTrustStatusPanel.cshtml", view, StringComparison.Ordinal);
    }
}
