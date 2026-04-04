using Xunit;

namespace Chummer.Tests;

public sealed class AccountBuildLabHandoffViewTests
{
    [Fact]
    public void AccountWorkDetailRendersPerOutputBuildLabFollowThroughCues()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("selectedBuildLabHandoff.Outputs.Take(8)", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.Outputs.Count - 8", view, StringComparison.Ordinal);
        Assert.Contains("@output.NextSafeAction", view, StringComparison.Ordinal);
        Assert.Contains("@output.ProvenanceSummary", view, StringComparison.Ordinal);
        Assert.Contains("@output.PublicationSummary", view, StringComparison.Ordinal);
        Assert.Contains("output.PublicationState", view, StringComparison.Ordinal);
        Assert.Contains("output.TrustBand", view, StringComparison.Ordinal);
        Assert.Contains("@output.AuditSummary", view, StringComparison.Ordinal);
        Assert.Contains("Publication:", view, StringComparison.Ordinal);
        Assert.Contains("Lane status:", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.ProgressionOutcomes.Take(3)", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.RuleEnvironmentDiff", view, StringComparison.Ordinal);
        Assert.Contains("Rule diff before", view, StringComparison.Ordinal);
        Assert.Contains("Rule diff after", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.CrewFitSummary", view, StringComparison.Ordinal);
        Assert.Contains("Crew fit", view, StringComparison.Ordinal);
        Assert.Contains("selectedBuildLabHandoff.PlannerCoverageLines.Take(5)", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountWorkspaceTravelModeRendersCacheFreshnessCues()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("selectedWorkspaceServerPlane.TravelMode.CacheFreshnessSummary", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceServerPlane.TravelMode.OfflineActionabilitySummary", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceServerPlane.TravelMode.FreshCacheDeviceCount", view, StringComparison.Ordinal);
        Assert.Contains("selectedWorkspaceServerPlane.TravelMode.StaleCacheDeviceCount", view, StringComparison.Ordinal);
        Assert.Contains("HumanizeStatus(device.Status, \"Status\")", view, StringComparison.Ordinal);
        Assert.Contains("Cache freshness", view, StringComparison.Ordinal);
        Assert.Contains("Offline actionability", view, StringComparison.Ordinal);
    }
}
