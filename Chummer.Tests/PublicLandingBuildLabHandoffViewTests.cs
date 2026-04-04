using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingBuildLabHandoffViewTests
{
    [Fact]
    public void SignedInHomeRailRendersBuildLabOutputFollowThroughCues()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("handoff.Outputs.Count > 0", view, StringComparison.Ordinal);
        Assert.Contains("handoff.Outputs.Take(8)", view, StringComparison.Ordinal);
        Assert.Contains("Output lanes continue:", view, StringComparison.Ordinal);
        Assert.Contains("handoff.Outputs.Count - 8", view, StringComparison.Ordinal);
        Assert.Contains("@output.NextSafeAction", view, StringComparison.Ordinal);
        Assert.Contains("@output.ProvenanceSummary", view, StringComparison.Ordinal);
        Assert.Contains("handoff.RuleEnvironmentDiff", view, StringComparison.Ordinal);
        Assert.Contains("Rule diff:", view, StringComparison.Ordinal);
        Assert.Contains("handoff.CrewFitSummary", view, StringComparison.Ordinal);
        Assert.Contains("Crew fit:", view, StringComparison.Ordinal);
        Assert.Contains("Output next:", view, StringComparison.Ordinal);
        Assert.Contains("Output provenance:", view, StringComparison.Ordinal);
    }
}
