using Xunit;

namespace Chummer.Tests;

public sealed class AccountBuildLabHandoffViewTests
{
    [Fact]
    public void AccountWorkDetailRendersPerOutputBuildLabFollowThroughCues()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("selectedBuildLabHandoff.Outputs.Take(4)", view, StringComparison.Ordinal);
        Assert.Contains("@output.NextSafeAction", view, StringComparison.Ordinal);
        Assert.Contains("@output.ProvenanceSummary", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.ProgressionOutcomes.Take(3)", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.RuleEnvironmentDiff", view, StringComparison.Ordinal);
        Assert.Contains("Rule diff before", view, StringComparison.Ordinal);
        Assert.Contains("Rule diff after", view, StringComparison.Ordinal);
    }
}
