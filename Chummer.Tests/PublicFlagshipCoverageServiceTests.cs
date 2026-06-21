using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicFlagshipCoverageServiceTests
{
    [Fact]
    public void LoadStrip_MapsHubMobileAndWorkbenchCoverageFromPublicProgressCanon()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();

        var service = new PublicFlagshipCoverageService(new PublicCanonFileLoader(configuration));

        var strip = service.LoadStrip();

        Assert.Equal("Whole-product frontier", strip.Eyebrow);
        Assert.Equal("Install, mobile return, and workbench polish belong together.", strip.Heading);
        Assert.DoesNotContain("truth", strip.Heading, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("rail", strip.Intro, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("lanes", strip.Intro, StringComparison.OrdinalIgnoreCase);
        Assert.Equal(3, strip.Cards.Count);

        Assert.Collection(
            strip.Cards,
            hub =>
            {
                Assert.Equal("hub_and_registry", hub.Id);
                Assert.Equal("Community Cloud & Publishing", hub.Label);
                Assert.Contains("public entry, publishing, registry", hub.Summary, StringComparison.Ordinal);
                Assert.Equal("Completion wave", hub.CurrentTitle);
                Assert.Equal("/downloads", hub.Href);
                Assert.Equal("Open install and account", hub.ActionLabel);
            },
            mobile =>
            {
                Assert.Equal("mobile_play_shell", mobile.Id);
                Assert.Equal("Live Play", mobile.Label);
                Assert.Contains("offline-resume play surfaces", mobile.Summary, StringComparison.Ordinal);
                Assert.Equal("Reliable session shell", mobile.TargetTitle);
                Assert.Equal("/now#real-mobile-prep", mobile.Href);
            },
            workbench =>
            {
                Assert.Equal("ui_kit_and_flagship_polish", workbench.Id);
                Assert.Equal("Workbench & Shared UI", workbench.Label);
                Assert.Contains("dense data UX", workbench.Summary, StringComparison.Ordinal);
                Assert.Equal("Polished workbench", workbench.TargetTitle);
                Assert.Equal("/what-is-chummer", workbench.Href);
            });
    }
}
