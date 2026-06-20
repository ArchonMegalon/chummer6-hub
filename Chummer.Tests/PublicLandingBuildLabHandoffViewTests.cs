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
        Assert.DoesNotContain("Output lanes continue:", view, StringComparison.Ordinal);
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
        Assert.Contains("Rule diff scope:", view, StringComparison.Ordinal);
        Assert.Contains("handoff.RuleEnvironmentDiff.BeforeScope", view, StringComparison.Ordinal);
        Assert.Contains("handoff.RuleEnvironmentDiff.AfterScope", view, StringComparison.Ordinal);
        Assert.Contains("handoff.CrewFitSummary", view, StringComparison.Ordinal);
        Assert.Contains("Crew fit:", view, StringComparison.Ordinal);
        Assert.Contains("handoff.ConditionalStateSummary", view, StringComparison.Ordinal);
        Assert.Contains("handoff.ConditionalStateLines.Take(2)", view, StringComparison.Ordinal);
        Assert.Contains("Conditional note:", view, StringComparison.Ordinal);
        Assert.Contains("handoff.SourceHintSummary", view, StringComparison.Ordinal);
        Assert.Contains("handoff.SourceHintLines.Take(2)", view, StringComparison.Ordinal);
        Assert.Contains("Source-linked hints:", view, StringComparison.Ordinal);
        Assert.Contains("Source hint:", view, StringComparison.Ordinal);
        Assert.Contains("handoff.BuildSurfaceSummary", view, StringComparison.Ordinal);
        Assert.Contains("handoff.BuildSurfaceLines.Take(2)", view, StringComparison.Ordinal);
        Assert.Contains("Build surface:", view, StringComparison.Ordinal);
        Assert.Contains("Build note:", view, StringComparison.Ordinal);
        Assert.Contains("handoff.ExchangeParitySummary", view, StringComparison.Ordinal);
        Assert.Contains("handoff.ExchangeParityLines.Take(2)", view, StringComparison.Ordinal);
        Assert.Contains("Exchange parity:", view, StringComparison.Ordinal);
        Assert.Contains("Parity note:", view, StringComparison.Ordinal);
        Assert.Contains("handoff.PortabilityPillarSummary", view, StringComparison.Ordinal);
        Assert.Contains("handoff.PortabilityPillarLines.Take(2)", view, StringComparison.Ordinal);
        Assert.Contains("Portability pillar:", view, StringComparison.Ordinal);
        Assert.Contains("Portability note:", view, StringComparison.Ordinal);
        Assert.Contains("handoff.PlannerCoverageLines.Take(2)", view, StringComparison.Ordinal);
        Assert.Contains("Planner note:", view, StringComparison.Ordinal);
        Assert.Contains("Output next:", view, StringComparison.Ordinal);
        Assert.Contains("Output source:", view, StringComparison.Ordinal);
        Assert.Contains("Output type:", view, StringComparison.Ordinal);
        Assert.Contains("Output publication:", view, StringComparison.Ordinal);
        Assert.Contains("Output status:", view, StringComparison.Ordinal);
        Assert.Contains("Output note:", view, StringComparison.Ordinal);
    }

    [Fact]
    public void SignedInHomeAftermathRailRendersRecapShelfCompatibilityAndLineageCues()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Compatibility: @leadAftermathShelfEntry.CompatibilitySummary", view, StringComparison.Ordinal);
        Assert.Contains("Lineage: @leadAftermathShelfEntry.LineageSummary", view, StringComparison.Ordinal);
    }
}
