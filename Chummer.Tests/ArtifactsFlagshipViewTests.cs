using Xunit;

namespace Chummer.Tests;

public sealed class ArtifactsFlagshipViewTests
{
    [Fact]
    public void ArtifactsPageUsesDetailFirstHeroAndRouteMap()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Shelf.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("ViewData[\"SurfaceClass\"] = \"surface-artifacts\";", view, StringComparison.Ordinal);
        Assert.Contains("Current usable detail surfaces", view, StringComparison.Ordinal);
        Assert.Contains("Open downloads", view, StringComparison.Ordinal);
        Assert.Contains("Pick details, downloads, signed-in history, or help without mixing their jobs.", view, StringComparison.Ordinal);
        Assert.Contains("Signed-in account return view", view, StringComparison.Ordinal);
    }

    [Fact]
    public void ArtifactsPageUsesPublicationAndContinuityShelvesInsteadOfAFlatProofDump()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Shelf.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Public publication detail", view, StringComparison.Ordinal);
        Assert.Contains("Signed-in account return view", view, StringComparison.Ordinal);
        Assert.Contains("Current usable detail surfaces", view, StringComparison.Ordinal);
        Assert.Contains("Opening next in the detail view", view, StringComparison.Ordinal);
        Assert.Contains("artifact-gallery__grid", view, StringComparison.Ordinal);
        Assert.Contains("ArtifactViewHref(view)", view, StringComparison.Ordinal);
    }
}
