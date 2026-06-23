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
        Assert.Contains("Current pages", view, StringComparison.Ordinal);
        Assert.Contains("Open downloads", view, StringComparison.Ordinal);
        Assert.Contains("Choose saved pages, downloads, account return, or help.", view, StringComparison.Ordinal);
        Assert.Contains("Open saved pages", view, StringComparison.Ordinal);
    }

    [Fact]
    public void ArtifactsPageUsesPublicationAndContinuityShelvesInsteadOfAFlatProofDump()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Shelf.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Public pages", view, StringComparison.Ordinal);
        Assert.Contains("Open saved pages", view, StringComparison.Ordinal);
        Assert.Contains("Current pages", view, StringComparison.Ordinal);
        Assert.Contains("Coming next", view, StringComparison.Ordinal);
        Assert.Contains("artifact-gallery__grid", view, StringComparison.Ordinal);
        Assert.Contains("ArtifactViewHref(view)", view, StringComparison.Ordinal);
    }
}
