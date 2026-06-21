using Xunit;

namespace Chummer.Tests;

public sealed class FaqFlagshipViewTests
{
    [Fact]
    public void FaqPageUsesARouteMapBeforeDroppingIntoAccordions()
    {
        string faqViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Faq.cshtml");
        string faqView = File.ReadAllText(faqViewPath);

        Assert.Contains("Get the answer or leave with the right next page.", faqView, StringComparison.Ordinal);
        Assert.Contains("route-choice-grid", faqView, StringComparison.Ordinal);
        Assert.Contains("Current status", faqView, StringComparison.Ordinal);
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

    [Fact]
    public void FaqAndHelpFieldsOverrideTheGlobalDarkFieldRule()
    {
        string cssPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "css", "site.css");
        string css = File.ReadAllText(cssPath);

        int globalFieldRuleIndex = css.IndexOf(".field input,\n.field select,\n.field textarea", StringComparison.Ordinal);
        int minimalFieldRuleIndex = css.IndexOf(".surface-minimal .field input", StringComparison.Ordinal);
        int faqHelpFieldRuleIndex = css.IndexOf(".surface-faq .field input", StringComparison.Ordinal);
        int faqHelpInteractiveRuleIndex = css.IndexOf(".surface-faq .field input:hover", StringComparison.Ordinal);
        int faqHelpOptionRuleIndex = css.IndexOf(".surface-faq .field select option", StringComparison.Ordinal);

        Assert.True(globalFieldRuleIndex >= 0, "Global field styling should remain explicit instead of inheriting browser defaults.");
        Assert.True(minimalFieldRuleIndex > globalFieldRuleIndex, "Minimal public pages must override the older dark field rule.");
        Assert.True(faqHelpFieldRuleIndex > minimalFieldRuleIndex, "FAQ/help fields must keep their own final readable override.");
        Assert.True(faqHelpInteractiveRuleIndex > faqHelpFieldRuleIndex, "FAQ/help hover and focus states must stay paired with normal input colors.");
        Assert.True(faqHelpOptionRuleIndex > faqHelpInteractiveRuleIndex, "FAQ/help dropdown options must be pinned after interactive states.");
        Assert.Contains(".surface-faq .field input", css, StringComparison.Ordinal);
        Assert.Contains(".route-help .field input", css, StringComparison.Ordinal);
        Assert.Contains(".surface-faq .field select option", css, StringComparison.Ordinal);
        Assert.Contains(".route-help .field select option", css, StringComparison.Ordinal);
        Assert.Contains("color-scheme: light;", css, StringComparison.Ordinal);
        Assert.Contains("background: #ffffff;", css, StringComparison.Ordinal);
        Assert.Contains("color: #151515;", css, StringComparison.Ordinal);
        Assert.Contains(".surface-faq .field textarea:focus", css, StringComparison.Ordinal);
        Assert.Contains(".route-help .field textarea:focus", css, StringComparison.Ordinal);
        Assert.Contains(".surface-faq .field select optgroup", css, StringComparison.Ordinal);
        Assert.Contains(".route-help .field select optgroup", css, StringComparison.Ordinal);
    }
}
