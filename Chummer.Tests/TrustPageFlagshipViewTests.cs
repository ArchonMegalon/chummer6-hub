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
        Assert.Contains("Pick the closest path.", trustView, StringComparison.Ordinal);
        Assert.Contains("minimal-help-grid", trustView, StringComparison.Ordinal);
        Assert.Contains("<h2>Contact</h2>", trustView, StringComparison.Ordinal);
        Assert.Contains("route-choice-grid--compact", trustView, StringComparison.Ordinal);
        Assert.Contains("ViewData[\"Title\"] = UndetectableHumanizerCopyAdapter.Humanize(Model.Heading);", trustView, StringComparison.Ordinal);
        Assert.Contains("@PublicText(Model.SupportIntake.Heading)", trustView, StringComparison.Ordinal);
        Assert.Contains("@PublicText(choice.Label)", trustView, StringComparison.Ordinal);
        Assert.Contains("Discord first. Keep the form for private details.", trustView, StringComparison.Ordinal);
        Assert.Contains("Public requests belong on <a class=\"inline-link\" href=\"/participate\">Participate</a>.", trustView, StringComparison.Ordinal);
        Assert.Contains("<details class=\"details-drawer minimal-help-card\" id=\"private-support-form\">", trustView, StringComparison.Ordinal);
        Assert.Contains("<summary>Private message</summary>", trustView, StringComparison.Ordinal);
        Assert.Contains("<label for=\"supportHeadId\">App copy</label>", trustView, StringComparison.Ordinal);
        Assert.Contains("<label for=\"supportInstallationId\">Installed copy</label>", trustView, StringComparison.Ordinal);
        Assert.Contains("Read the short privacy summary first, then the full policy.", trustView, StringComparison.Ordinal);
        Assert.Contains("Read the short rules summary first, then the full terms.", trustView, StringComparison.Ordinal);
        Assert.Contains("else if (!contactPage)", trustView, StringComparison.Ordinal);
        Assert.Contains("<div class=\"minimal-actions\">", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("<h2>Details</h2>", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("Need a different path?", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("one fallback", trustView, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Fallback:", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("Or:", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain(">Desktop head</label>", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain(">Install id</label>", trustView, StringComparison.Ordinal);
    }

    [Fact]
    public void ContactSupportPageShowsRouteChoicesBeforeTheFormFields()
    {
        string trustViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml");
        string trustView = File.ReadAllText(trustViewPath);

        int routeChoiceIndex = trustView.IndexOf("Discord first. Keep the form for private details.", StringComparison.Ordinal);
        int formIndex = trustView.IndexOf("<form class=\"settings-form\"", StringComparison.Ordinal);

        Assert.True(routeChoiceIndex >= 0, "contact support view should show the routing choices before the form");
        Assert.True(formIndex >= 0, "contact support form should still exist");
        Assert.True(routeChoiceIndex < formIndex, "route choices should appear before the support form");
        Assert.Contains("One problem per message.", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("Case-type guide", trustView, StringComparison.Ordinal);
    }
}
