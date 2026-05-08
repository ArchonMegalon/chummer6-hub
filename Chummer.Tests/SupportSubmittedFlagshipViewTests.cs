using Xunit;

namespace Chummer.Tests;

public sealed class SupportSubmittedFlagshipViewTests
{
    [Fact]
    public void SupportSubmittedPageUsesARoutePackAndResponseHelperPack()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "SupportSubmitted.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Pick the next support page without losing continuity.", view, StringComparison.Ordinal);
        Assert.Contains("Response helper pack", view, StringComparison.Ordinal);
        Assert.Contains("Keep the case moving on the same support path.", view, StringComparison.Ordinal);
        Assert.Contains("Open what works today", view, StringComparison.Ordinal);
        Assert.Contains("No browser-only recovery", view, StringComparison.Ordinal);
    }

    [Fact]
    public void SupportSubmittedPageKeepsTimelineAndSavedEvidenceAsDrawers()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "SupportSubmitted.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Case timeline", view, StringComparison.Ordinal);
        Assert.Contains("Model.TrackedCaseSummary?.TimelineHighlights is { Count: > 0 }", view, StringComparison.Ordinal);
        Assert.Contains("Saved evidence", view, StringComparison.Ordinal);
        Assert.DoesNotContain("_SignedInTrustStatusPanel.cshtml", view, StringComparison.Ordinal);
    }
}
