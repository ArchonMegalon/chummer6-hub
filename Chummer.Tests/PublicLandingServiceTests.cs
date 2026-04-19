using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingServiceTests
{
    [Fact]
    public void LoadSurface_AllowsPublishedArtifactCompatibilityRoutes()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new PublicLandingService(
            new PublicCanonFileLoader(configuration),
            new PublicActionResolver());

        var surface = service.LoadSurface();

        Assert.Contains(surface.FeatureCards, static card =>
            string.Equals(card.DetailRoute, "/artifacts/campaign-primer-video", StringComparison.Ordinal));
        Assert.Contains(surface.FeatureCards, static card =>
            string.Equals(card.DetailRoute, "/artifacts/mission-brief-video", StringComparison.Ordinal));
    }
}
