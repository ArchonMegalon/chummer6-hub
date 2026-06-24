using Xunit;

namespace Chummer.Tests;

public sealed class TrustPageFlagshipViewTests
{
    [Fact]
    public void TrustPageBranchesIntoRouteSpecificHelpContactAndPolicySystems()
    {
        string trustViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml");
        string trustView = File.ReadAllText(trustViewPath);

        Assert.Contains("Pick the problem", trustView, StringComparison.Ordinal);
        Assert.Contains("Each card starts with the best first step. Use the second link only if needed.", trustView, StringComparison.Ordinal);
        Assert.Contains("minimal-help-card__list", trustView, StringComparison.Ordinal);
        Assert.Contains("aria-label=\"Quick notes\"", trustView, StringComparison.Ordinal);
        Assert.Contains("If that does not fit:", trustView, StringComparison.Ordinal);
        Assert.Contains("Pick the path", trustView, StringComparison.Ordinal);
        Assert.Contains("route-choice-grid--compact", trustView, StringComparison.Ordinal);
        Assert.Contains("ViewData[\"Title\"] = UndetectableHumanizerCopyAdapter.Humanize(Model.Heading);", trustView, StringComparison.Ordinal);
        Assert.Contains("@PublicText(Model.SupportIntake.Heading)", trustView, StringComparison.Ordinal);
        Assert.Contains("@PublicText(Model.SupportIntake.AccountSupportLabel)", trustView, StringComparison.Ordinal);
        Assert.Contains("@PublicText(choice.Label)", trustView, StringComparison.Ordinal);
        Assert.Contains("Use Participate for ideas and safe public bugs", trustView, StringComparison.Ordinal);
        Assert.Contains("Read the short privacy summary first, then the full policy.", trustView, StringComparison.Ordinal);
        Assert.Contains("Read the short rules summary first, then the full terms.", trustView, StringComparison.Ordinal);
        Assert.Contains("else if (!contactPage)", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("<h2>Details</h2>", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("Need a different path?", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("one fallback", trustView, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Fallback:", trustView, StringComparison.Ordinal);
    }

    [Fact]
    public void ContactSupportPageShowsRouteChoicesBeforeTheFormFields()
    {
        string trustViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml");
        string trustView = File.ReadAllText(trustViewPath);

        int routeChoiceIndex = trustView.IndexOf("Use Participate for ideas and safe public bugs", StringComparison.Ordinal);
        int formIndex = trustView.IndexOf("<form class=\"settings-form\"", StringComparison.Ordinal);

        Assert.True(routeChoiceIndex >= 0, "contact support view should show the routing choices before the form");
        Assert.True(formIndex >= 0, "contact support form should still exist");
        Assert.True(routeChoiceIndex < formIndex, "route choices should appear before the support form");
        Assert.Contains("Keep one issue per case so the reply stays clear.", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("Case-type guide", trustView, StringComparison.Ordinal);
    }
}
