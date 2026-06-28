using Xunit;

namespace Chummer.Tests;

public sealed class RoadmapMilestoneProjectionViewTests
{
    [Fact]
    public void RoadmapViewStaysMinimalWhenTheLiveBoardFallsBack()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Roadmap.cshtml");
        string source = File.ReadAllText(viewPath);

        Assert.Contains("Now and next.", source, StringComparison.Ordinal);
        Assert.Contains("Current requests live in Participate.", source, StringComparison.Ordinal);
        Assert.Contains("Planned work is here. Shipped work stays in Changelog.", source, StringComparison.Ordinal);
        Assert.Contains("Current work opens below.", source, StringComparison.Ordinal);
        Assert.Contains("Changelog", source, StringComparison.Ordinal);
        Assert.DoesNotContain("Model.Milestones", source, StringComparison.Ordinal);
        Assert.DoesNotContain("Top requests", source, StringComparison.Ordinal);
        Assert.DoesNotContain("ProductLift owns the roadmap.", source, StringComparison.Ordinal);
        Assert.DoesNotContain("Private issue", source, StringComparison.Ordinal);
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
