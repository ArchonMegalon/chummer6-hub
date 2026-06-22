using Xunit;

namespace Chummer.Tests;

public sealed class ArtifactsFlagshipViewTests
{
    [Fact]
    public void ArtifactsPageUsesDetailFirstHeroAndRouteMap()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Shelf.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("ViewData[\"SurfaceClass\"] = \"surface-artifacts surface-minimal\";", view, StringComparison.Ordinal);
        Assert.Contains("Current library pages", view, StringComparison.Ordinal);
        Assert.Contains("Open downloads", view, StringComparison.Ordinal);
        Assert.Contains("Choose library, downloads, account return, or help.", view, StringComparison.Ordinal);
        Assert.Contains("Your library", view, StringComparison.Ordinal);
    }

    [Fact]
    public void ArtifactsPageUsesPublicationAndContinuityShelvesInsteadOfAFlatProofDump()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Shelf.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Public library", view, StringComparison.Ordinal);
        Assert.Contains("Your library", view, StringComparison.Ordinal);
        Assert.Contains("Current library pages", view, StringComparison.Ordinal);
        Assert.Contains("Opening next", view, StringComparison.Ordinal);
        Assert.Contains("artifact-gallery__grid", view, StringComparison.Ordinal);
        Assert.Contains("ArtifactViewHref(view)", view, StringComparison.Ordinal);
    }
}
