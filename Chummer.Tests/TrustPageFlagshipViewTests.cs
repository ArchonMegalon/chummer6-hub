using Xunit;

namespace Chummer.Tests;

public sealed class TrustPageFlagshipViewTests
{
    [Fact]
    public void TrustPageBranchesIntoRouteSpecificHelpContactAndPolicySystems()
    {
        string trustViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml");
        string trustView = File.ReadAllText(trustViewPath);

        Assert.Contains("<h2>Start here</h2>", trustView, StringComparison.Ordinal);
        Assert.Contains("Pick the next step.", trustView, StringComparison.Ordinal);
        Assert.Contains("minimal-help-grid", trustView, StringComparison.Ordinal);
        Assert.Contains("<h2>Discord</h2>", trustView, StringComparison.Ordinal);
        Assert.Contains("route-choice-grid--compact", trustView, StringComparison.Ordinal);
        Assert.Contains("ViewData[\"Title\"] = UndetectableHumanizerCopyAdapter.Humanize(Model.Heading);", trustView, StringComparison.Ordinal);
        Assert.Contains("@PublicText(choice.Label)", trustView, StringComparison.Ordinal);
        Assert.Contains("Normal questions and feedback belong in the Chummer5 server.", trustView, StringComparison.Ordinal);
        Assert.Contains("Chummer5 Discord", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("<details class=\"details-drawer minimal-help-card\" id=\"private-support-form\">", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("<summary>Private message</summary>", trustView, StringComparison.Ordinal);
        Assert.Contains("Read the short privacy summary first, then the full policy.", trustView, StringComparison.Ordinal);
        Assert.Contains("Read the short rules summary first, then the full terms.", trustView, StringComparison.Ordinal);
        Assert.Contains("else if (!contactPage)", trustView, StringComparison.Ordinal);
        Assert.Contains("route-choice-card", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("<h2>Details</h2>", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("Need a different path?", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("one fallback", trustView, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Fallback:", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("Or:", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain(">Desktop head</label>", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain(">Install id</label>", trustView, StringComparison.Ordinal);
    }

    [Fact]
    public void ContactPageShowsOnlyDiscordRoute()
    {
        string trustViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml");
        string trustView = File.ReadAllText(trustViewPath);

        Assert.Contains("Title: \"Chummer5 Discord\"", trustView, StringComparison.Ordinal);
        Assert.Contains("Href: \"https://discord.gg/chummer\"", trustView, StringComparison.Ordinal);
        Assert.Contains("Label: \"Open Discord\"", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("Title: \"Private form\"", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("Open private form", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("<form class=\"settings-form\"", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("One problem per message keeps the reply clear.", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("Case-type guide", trustView, StringComparison.Ordinal);
    }
}
