using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingServiceTests
{
    private static PublicLandingService BuildService(string canonRoot = null!)
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = string.IsNullOrWhiteSpace(canonRoot) ? RepoPaths.Root : canonRoot
            })
            .Build();

        return new PublicLandingService(
            new PublicCanonFileLoader(configuration),
            new PublicActionResolver());
    }

    [Fact]
    public void LoadSurface_AllowsPublishedArtifactCompatibilityRoutes()
    {
        var surface = BuildService().LoadSurface();

        Assert.Contains(surface.FeatureCards, static card =>
            string.Equals(card.DetailRoute, "/artifacts/campaign-primer-video", StringComparison.Ordinal));
        Assert.Contains(surface.FeatureCards, static card =>
            string.Equals(card.DetailRoute, "/artifacts/mission-brief-video", StringComparison.Ordinal));
    }

    [Fact]
    public void LoadSurface_IncludesCurrentRoadmapAndArtifactBridgeRoutes()
    {
        var surface = BuildService().LoadSurface();

        Assert.Contains(surface.PublicRoutes, static route =>
            string.Equals(route.Path, "/packages", StringComparison.Ordinal));
        Assert.Contains(surface.PublicRoutes, static route =>
            string.Equals(route.Path, "/mobile", StringComparison.Ordinal));
        Assert.Contains(surface.PublicRoutes, static route =>
            string.Equals(route.Path, "/play", StringComparison.Ordinal));
        Assert.Contains(surface.PublicRoutes, static route =>
            string.Equals(route.Path, "/downloads/concierge", StringComparison.Ordinal));
        Assert.Contains(surface.PublicRoutes, static route =>
            string.Equals(route.Path, "/roadmap/black-ledger", StringComparison.Ordinal));
        Assert.Contains(surface.PublicRoutes, static route =>
            string.Equals(route.Path, "/roadmap/community-hub", StringComparison.Ordinal));

        var communityHub = Assert.Single(surface.FeatureCards, static card =>
            string.Equals(card.Id, "feature_community_hub", StringComparison.Ordinal));
        var blackLedger = Assert.Single(surface.FeatureCards, static card =>
            string.Equals(card.Id, "horizon_black_ledger", StringComparison.Ordinal));

        Assert.Equal("/community", communityHub.DetailRoute);
        Assert.Equal("/community", communityHub.DetailPrimaryHref);
        Assert.Equal("/community/open-run-network", communityHub.FallbackRoute);
        Assert.Equal("/ledger", blackLedger.DetailRoute);
        Assert.Equal("/ledger/factions", blackLedger.DetailPrimaryHref);
    }

    [Fact]
    public void FindCardForDetailPage_PreservesDetailRouteAndResolvesExactRoadmapHref()
    {
        var service = BuildService();
        var surface = service.LoadSurface();

        var artifact = service.FindCardForDetailPage(surface, "/artifacts/runsite-pack");
        var roadmap = service.FindCardForDetailPage(surface, "/roadmap/runsite");

        Assert.NotNull(artifact);
        Assert.NotNull(roadmap);
        Assert.Equal(artifact.Id, roadmap.Id);
        Assert.Equal("featured_artifacts", roadmap.Bucket);
        Assert.Equal("/artifacts/runsite-pack", roadmap.DetailRoute);
        Assert.Equal("/roadmap/runsite", roadmap.Href);
        Assert.Equal("/roadmap/runsite", roadmap.DetailPrimaryHref);
    }

    [Fact]
    public void FindCardForDetailPage_DoesNotTreatActionRoutesAsDetailAliases()
    {
        var service = BuildService();
        var surface = service.LoadSurface();
        var runsite = Assert.Single(surface.FeatureCards, static card =>
            string.Equals(card.DetailRoute, "/artifacts/runsite-pack", StringComparison.Ordinal));
        var bridgeCard = runsite with
        {
            Href = "/roadmap/exact-href",
            DetailRoute = "/artifacts/exact-href",
            GuestHref = "/roadmap/guest-action",
            RegisteredHref = "/roadmap/registered-action",
            DetailPrimaryHref = "/roadmap/exact-href",
            FallbackRoute = "/roadmap/fallback-action"
        };
        var isolatedSurface = surface with { FeatureCards = new[] { bridgeCard } };

        Assert.Equal(bridgeCard.Id, service.FindCardForDetailPage(isolatedSurface, bridgeCard.Href)?.Id);
        Assert.Null(service.FindCardForDetailPage(isolatedSurface, bridgeCard.GuestHref!));
        Assert.Null(service.FindCardForDetailPage(isolatedSurface, bridgeCard.RegisteredHref!));
        Assert.Null(service.FindCardForDetailPage(isolatedSurface, bridgeCard.FallbackRoute!));

        var unrelatedHrefSurface = surface with
        {
            FeatureCards = new[]
            {
                bridgeCard with
                {
                    Href = "/downloads",
                    DetailPrimaryHref = "/downloads"
                }
            }
        };
        Assert.Null(service.FindCardForDetailPage(unrelatedHrefSurface, "/downloads"));

        var wrongBucketSurface = surface with
        {
            FeatureCards = new[]
            {
                bridgeCard with { Bucket = "coming_next" }
            }
        };
        Assert.Null(service.FindCardForDetailPage(wrongBucketSurface, bridgeCard.Href));

        var nonArtifactDetailSurface = surface with
        {
            FeatureCards = new[] { bridgeCard with { DetailRoute = "/roadmap/canonical-detail" } }
        };
        Assert.Null(service.FindCardForDetailPage(nonArtifactDetailSurface, bridgeCard.Href));

        var mismatchedPrimarySurface = surface with
        {
            FeatureCards = new[] { bridgeCard with { DetailPrimaryHref = "/roadmap/other-primary" } }
        };
        Assert.Null(service.FindCardForDetailPage(mismatchedPrimarySurface, bridgeCard.Href));

        var missingPrimarySurface = surface with
        {
            FeatureCards = new[] { bridgeCard with { DetailPrimaryHref = null } }
        };
        Assert.Null(service.FindCardForDetailPage(missingPrimarySurface, bridgeCard.Href));
    }

    [Fact]
    public void CardsForBucket_IncludesPublicReleaseArtifactCards()
    {
        var service = BuildService();
        var surface = service.LoadSurface();

        Assert.Contains(surface.FeatureCards, static card =>
            string.Equals(card.Id, "artifact_mac_release_pipeline", StringComparison.Ordinal));

        var publicArtifacts = service.CardsForBucket(surface, "featured_artifacts");

        Assert.Contains(publicArtifacts, static card =>
            string.Equals(card.Id, "artifact_mac_release_pipeline", StringComparison.Ordinal));
        Assert.Contains(publicArtifacts, static card =>
            string.Equals(card.Id, "artifact_preview_build", StringComparison.Ordinal));
    }

    [Fact]
    public void PublicLandingCanonAcceptsCurrentProofBoundaryFields()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var loader = new PublicCanonFileLoader(configuration);
        var document = loader.LoadRequiredYaml<PublicLandingManifestDocument>(".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml");

        Assert.Contains("player can actually try today", document.ProductProofScopeLine, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Experimental surfaces stay off the main path", document.ProductFlagshipBoundaryLine, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(document.PublicRoutes!, static route =>
            string.Equals(route.Path, "/packages", StringComparison.Ordinal)
            && string.Equals(route.Purpose, "package_browser", StringComparison.Ordinal));
        Assert.Contains(document.PublicRoutes!, static route =>
            string.Equals(route.Path, "/downloads/concierge", StringComparison.Ordinal)
            && string.Equals(route.Purpose, "guided_download_wrapper", StringComparison.Ordinal));
        Assert.Contains(document.PublicRoutes!, static route =>
            string.Equals(route.Path, "/horizons", StringComparison.Ordinal)
            && string.Equals(route.Purpose, "working_horizons_summary", StringComparison.Ordinal));
        Assert.Contains(document.PublicRoutes!, static route =>
            string.Equals(route.Path, "/player", StringComparison.Ordinal)
            && string.Equals(route.RequiredRedirectLocationPrefix, "/mobile/player", StringComparison.Ordinal));
        Assert.Contains(document.PublicRoutes!, static route =>
            string.Equals(route.Path, "/jammer", StringComparison.Ordinal)
            && string.Equals(route.RequiredRedirectLocationPrefix, "/mobile/player", StringComparison.Ordinal));
        Assert.Contains(document.PublicRoutes!, static route =>
            string.Equals(route.Path, "/gm", StringComparison.Ordinal)
            && string.Equals(route.RequiredRedirectLocationPrefix, "/mobile/gm", StringComparison.Ordinal));
        Assert.Contains(document.RegisteredRoutes!, static route =>
            string.Equals(route.Path, "/account/packages", StringComparison.Ordinal)
            && string.Equals(route.Purpose, "tracked_package_summary", StringComparison.Ordinal));
    }

    [Fact]
    public void LoadSurface_SupportsPublishedAppStyleCanonRoot()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), $"chummer-public-canon-{Guid.NewGuid():N}");

        try
        {
            CopyDirectory(
                RepoPaths.FromRoot(".codex-design", "product"),
                Path.Combine(tempRoot, ".codex-design", "product"));
            CopyDirectory(
                RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot"),
                Path.Combine(tempRoot, "wwwroot"));

            var surface = BuildService(tempRoot).LoadSurface();

            Assert.Equal("chummer.run", surface.Surface);
            Assert.Contains(surface.FeatureCards, static card =>
                string.Equals(card.Id, "horizon_black_ledger", StringComparison.Ordinal));
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void CopyDirectory(string sourceRoot, string destinationRoot)
    {
        foreach (string directory in Directory.GetDirectories(sourceRoot, "*", SearchOption.AllDirectories))
        {
            Directory.CreateDirectory(directory.Replace(sourceRoot, destinationRoot, StringComparison.Ordinal));
        }

        Directory.CreateDirectory(destinationRoot);
        foreach (string file in Directory.GetFiles(sourceRoot, "*", SearchOption.AllDirectories))
        {
            string destination = file.Replace(sourceRoot, destinationRoot, StringComparison.Ordinal);
            Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
            File.Copy(file, destination, overwrite: true);
        }
    }
}
