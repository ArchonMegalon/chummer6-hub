using Xunit;

namespace Chummer.Tests;

public sealed class RoadmapMilestoneProjectionViewTests
{
    [Fact]
    public void RoadmapViewIncludesMilestoneLedgerLabels()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Roadmap.cshtml");
        string source = File.ReadAllText(viewPath);

        Assert.Contains("roadmap-signal", source, StringComparison.Ordinal);
        Assert.Contains("roadmap-signal-grid", source, StringComparison.Ordinal);
        Assert.Contains("Feedback, planning, shipped proof, and private help stay on different pages.", source, StringComparison.Ordinal);
        Assert.Contains("Votes inform demand", source, StringComparison.Ordinal);
        Assert.Contains("Open changelog", source, StringComparison.Ordinal);
        Assert.Contains("Model.Milestones", source, StringComparison.Ordinal);
        Assert.Contains("Milestone ledger", source, StringComparison.Ordinal);
        Assert.Contains("Difficulty:", source, StringComparison.Ordinal);
        Assert.Contains("Claimed:", source, StringComparison.Ordinal);
        Assert.Contains("Dependencies:", source, StringComparison.Ordinal);
        Assert.Contains("milestone-drawer__tease", source, StringComparison.Ordinal);
    }

    [Fact]
    public void HomeSurfaceNoLongerCarriesThePrivateMilestoneShelf()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string homeViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml");
        string controllerSource = File.ReadAllText(controllerPath);
        string homeSource = File.ReadAllText(homeViewPath);

        Assert.DoesNotContain("Model.TiborMilestones", homeSource, StringComparison.Ordinal);
        Assert.DoesNotContain("milestone-shelf", homeSource, StringComparison.Ordinal);
        Assert.DoesNotContain("BuildTiborHomeMilestones", controllerSource, StringComparison.Ordinal);
        Assert.Contains("BuildRoadmapMilestones", controllerSource, StringComparison.Ordinal);
    }
}
