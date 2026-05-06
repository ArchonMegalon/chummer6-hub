using Xunit;

namespace Chummer.Tests;

public sealed class ArtifactsFlagshipViewTests
{
    [Fact]
    public void ArtifactsPageUsesProofFirstHeroAndRouteMap()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Shelf.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("ViewData[\"SurfaceClass\"] = \"surface-artifacts\";", view, StringComparison.Ordinal);
        Assert.Contains("Inspect proof gallery", view, StringComparison.Ordinal);
        Assert.Contains("Open downloads", view, StringComparison.Ordinal);
        Assert.Contains("Pick proof, downloads, signed-in continuity, or help without mixing their jobs.", view, StringComparison.Ordinal);
        Assert.Contains("Install rail stays primary", view, StringComparison.Ordinal);
    }

    [Fact]
    public void ArtifactsPageUsesPublicationAndContinuityShelvesInsteadOfAFlatProofDump()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Shelf.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Public publication shelf", view, StringComparison.Ordinal);
        Assert.Contains("Signed-in continuity shelf", view, StringComparison.Ordinal);
        Assert.Contains("Current usable proof surfaces", view, StringComparison.Ordinal);
        Assert.Contains("Opening next on the shelf", view, StringComparison.Ordinal);
        Assert.Contains("artifact-gallery__grid", view, StringComparison.Ordinal);
        Assert.Contains("ArtifactViewHref(view)", view, StringComparison.Ordinal);
    }
}
