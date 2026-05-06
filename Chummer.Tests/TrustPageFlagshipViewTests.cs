using Xunit;

namespace Chummer.Tests;

public sealed class TrustPageFlagshipViewTests
{
    [Fact]
    public void TrustPageBranchesIntoRouteSpecificHelpContactAndPolicySystems()
    {
        string trustViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml");
        string trustView = File.ReadAllText(trustViewPath);

        Assert.Contains("Choose the next safe help path.", trustView, StringComparison.Ordinal);
        Assert.Contains("First-party help keeps the next step concrete.", trustView, StringComparison.Ordinal);
        Assert.Contains("Public signal, private support, tracked return, and install recovery stay separate.", trustView, StringComparison.Ordinal);
        Assert.Contains("Read the trust boundary first, then the full policy.", trustView, StringComparison.Ordinal);
        Assert.Contains("Read the rule boundary first, then the full terms.", trustView, StringComparison.Ordinal);
        Assert.Contains("else if (!contactPage)", trustView, StringComparison.Ordinal);
    }

    [Fact]
    public void ContactSupportFormShowsCaseTypeGuideBeforeTheFormFields()
    {
        string trustViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml");
        string trustView = File.ReadAllText(trustViewPath);

        int caseTypeGuideIndex = trustView.IndexOf("Choose the lane that fits the issue before you attach logs", StringComparison.Ordinal);
        int formIndex = trustView.IndexOf("<form class=\"settings-form\"", StringComparison.Ordinal);

        Assert.True(caseTypeGuideIndex >= 0, "contact support view should explain the case lanes before the form");
        Assert.True(formIndex >= 0, "contact support form should still exist");
        Assert.True(caseTypeGuideIndex < formIndex, "case-type guide should appear before the support form");
        Assert.Contains("Safe public feedback should start on Fixer Board. Choose this form only when the issue needs private or account-linked follow-up.", trustView, StringComparison.Ordinal);
        Assert.Contains("Model.SupportIntake.Options", trustView, StringComparison.Ordinal);
    }
}
