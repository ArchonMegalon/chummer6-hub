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
        Assert.Contains("BuildLabOutputLaneLabel(output.Kind)", view, StringComparison.Ordinal);
        Assert.Contains("@output.PublicationSummary", view, StringComparison.Ordinal);
        Assert.Contains("output.PublicationState", view, StringComparison.Ordinal);
        Assert.Contains("output.TrustBand", view, StringComparison.Ordinal);
        Assert.Contains("@output.AuditSummary", view, StringComparison.Ordinal);
        Assert.Contains("handoff.RuleEnvironmentDiff", view, StringComparison.Ordinal);
        Assert.Contains("Rule diff:", view, StringComparison.Ordinal);
        Assert.Contains("handoff.CrewFitSummary", view, StringComparison.Ordinal);
        Assert.Contains("Crew fit:", view, StringComparison.Ordinal);
        Assert.Contains("handoff.ConditionalStateSummary", view, StringComparison.Ordinal);
        Assert.Contains("handoff.ConditionalStateLines.Take(2)", view, StringComparison.Ordinal);
        Assert.Contains("Conditional lane:", view, StringComparison.Ordinal);
        Assert.Contains("handoff.PlannerCoverageLines.Take(2)", view, StringComparison.Ordinal);
        Assert.Contains("Planner lane:", view, StringComparison.Ordinal);
        Assert.Contains("Output next:", view, StringComparison.Ordinal);
        Assert.Contains("Output provenance:", view, StringComparison.Ordinal);
        Assert.Contains("Output lane:", view, StringComparison.Ordinal);
        Assert.Contains("Output publication:", view, StringComparison.Ordinal);
        Assert.Contains("Output lane status:", view, StringComparison.Ordinal);
        Assert.Contains("Output audit:", view, StringComparison.Ordinal);
    }
}
