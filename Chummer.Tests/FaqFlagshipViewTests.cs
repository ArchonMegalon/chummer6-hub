using Xunit;

namespace Chummer.Tests;

public sealed class FaqFlagshipViewTests
{
    [Fact]
    public void FaqPageUsesARouteMapBeforeDroppingIntoAccordions()
    {
        string faqViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Faq.cshtml");
        string faqView = File.ReadAllText(faqViewPath);

        Assert.Contains("Get the answer or leave with the right next route.", faqView, StringComparison.Ordinal);
        Assert.Contains("route-choice-grid", faqView, StringComparison.Ordinal);
        Assert.Contains("Reality check", faqView, StringComparison.Ordinal);
        Assert.Contains("Private help", faqView, StringComparison.Ordinal);
        Assert.Contains("Open support intake", faqView, StringComparison.Ordinal);
    }

    [Fact]
    public void FaqSearchDeckStillAppearsBeforeTheGroupedAnswerSections()
    {
        string faqViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Faq.cshtml");
        string faqView = File.ReadAllText(faqViewPath);

        int searchDeckIndex = faqView.IndexOf("Plain answers first, deeper help right behind them", StringComparison.Ordinal);
        int firstSectionIndex = faqView.IndexOf("data-faq-section", StringComparison.Ordinal);

        Assert.True(searchDeckIndex >= 0, "FAQ should explain the search deck");
        Assert.True(firstSectionIndex >= 0, "FAQ should still render grouped answer sections");
        Assert.True(searchDeckIndex < firstSectionIndex, "FAQ search deck should appear before the grouped answer sections");
        Assert.Contains("Still stuck? Open support", faqView, StringComparison.Ordinal);
        Assert.Contains("href=\"/help\"", faqView, StringComparison.Ordinal);
    }
}
