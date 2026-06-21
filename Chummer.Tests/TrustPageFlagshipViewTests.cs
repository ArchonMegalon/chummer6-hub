using Xunit;

namespace Chummer.Tests;

public sealed class TrustPageFlagshipViewTests
{
    [Fact]
    public void TrustPageBranchesIntoRouteSpecificHelpContactAndPolicySystems()
    {
        string trustViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml");
        string trustView = File.ReadAllText(trustViewPath);

        Assert.Contains("Choose the right path", trustView, StringComparison.Ordinal);
        Assert.Contains("Each path has a clear next step and a second option if that does not fit.", trustView, StringComparison.Ordinal);
        Assert.Contains("If that does not fit:", trustView, StringComparison.Ordinal);
        Assert.Contains("Public feedback, account return, and install recovery stay nearby.", trustView, StringComparison.Ordinal);
        Assert.Contains("ViewData[\"Title\"] = PublicFacingCopyHumanizer.Clean(Model.Heading);", trustView, StringComparison.Ordinal);
        Assert.Contains("@PublicText(Model.SupportIntake.Heading)", trustView, StringComparison.Ordinal);
        Assert.Contains("@PublicText(Model.SupportIntake.AccountSupportLabel)", trustView, StringComparison.Ordinal);
        Assert.Contains("@PublicText(choice.Label)", trustView, StringComparison.Ordinal);
        Assert.Contains("Safe public feedback should start on the public feedback page", trustView, StringComparison.Ordinal);
        Assert.Contains("Read the trust boundary first, then the full policy.", trustView, StringComparison.Ordinal);
        Assert.Contains("Read the rule boundary first, then the full terms.", trustView, StringComparison.Ordinal);
        Assert.Contains("else if (!contactPage)", trustView, StringComparison.Ordinal);
        Assert.DoesNotContain("one fallback", trustView, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Fallback:", trustView, StringComparison.Ordinal);
    }

    [Fact]
    public void ContactSupportFormShowsCaseTypeGuideBeforeTheFormFields()
    {
        string trustViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml");
        string trustView = File.ReadAllText(trustViewPath);

        int caseTypeGuideIndex = trustView.IndexOf("Safe public feedback should start on the public feedback page", StringComparison.Ordinal);
        int formIndex = trustView.IndexOf("<form class=\"settings-form\"", StringComparison.Ordinal);

        Assert.True(caseTypeGuideIndex >= 0, "contact support view should explain the case choices before the form");
        Assert.True(formIndex >= 0, "contact support form should still exist");
        Assert.True(caseTypeGuideIndex < formIndex, "case-type guide should appear before the support form");
        Assert.Contains("Safe public feedback should start on the public feedback page. Choose this form only when the issue needs private or account-linked follow-up.", trustView, StringComparison.Ordinal);
        Assert.Contains("Model.SupportIntake.Options", trustView, StringComparison.Ordinal);
    }
}
