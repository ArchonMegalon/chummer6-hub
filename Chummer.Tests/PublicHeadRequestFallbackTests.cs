using Xunit;

namespace Chummer.Tests;

public sealed class PublicHeadRequestFallbackTests
{
    [Fact]
    public void PublicEdgeDeclaresHeadRoutesOnUserFacingPages()
    {
        string publicLandingController = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string billingController = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "BrilliantDirectoriesBillingController.cs"));

        string[] publicPageRoutes =
        [
            "/",
            "/downloads",
            "/status",
            "/help",
            "/faq",
            "/privacy",
            "/terms",
            "/contact",
            "/participate",
            "/participate/board",
            "/roadmap",
            "/changelog",
            "/partizipate"
        ];

        foreach (string route in publicPageRoutes)
        {
            Assert.Contains($"[HttpHead(\"{route}\")]", publicLandingController, StringComparison.Ordinal);
        }

        Assert.Contains("[HttpHead(\"/account/billing\")]", billingController, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicEdgeHealthEndpointAcceptsHeadExplicitly()
    {
        string program = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Program.cs"));

        Assert.Contains("app.MapMethods(\"/api/health\", new[] { HttpMethods.Get, HttpMethods.Head }", program, StringComparison.Ordinal);
        Assert.DoesNotContain("context.Request.Method = HttpMethods.Get;", program, StringComparison.Ordinal);
        Assert.DoesNotContain("ShouldServeHeadFromGet", program, StringComparison.Ordinal);
    }
}
