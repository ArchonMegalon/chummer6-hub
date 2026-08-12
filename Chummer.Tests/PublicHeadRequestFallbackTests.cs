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
            "/account/delete",
            "/terms",
            "/contact",
            "/mobile",
            "/pwa",
            "/play",
            "/player",
            "/jammer",
            "/gm",
            "/observer",
            "/play/anarchy",
            "/build",
            "/alice",
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
    public void PublicAccountDeletionPageIsDiscoverableAndKeepsLocalFilesOutOfScope()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));

        Assert.Contains("[HttpGet(\"/account/delete\")]", controller, StringComparison.Ordinal);
        Assert.Contains("Request deletion without reopening the app", controller, StringComparison.Ordinal);
        Assert.Contains("/login?next=%2Faccount%2Fsupport", controller, StringComparison.Ordinal);
        Assert.Contains("Local-only files remain under the user's Android or desktop storage control.", controller, StringComparison.Ordinal);
        Assert.Contains("new TrustPageActionViewModel(\"Request account deletion\", \"/account/delete\", \"secondary\")", controller, StringComparison.Ordinal);
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
