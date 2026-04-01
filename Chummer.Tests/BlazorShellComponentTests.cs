using Xunit;

namespace Chummer.Tests;

public sealed class BlazorShellComponentTests
{
    [Fact]
    public void SignedInTrustPanelPartialExists()
    {
        string partialPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_SignedInTrustStatusPanel.cshtml");

        Assert.True(File.Exists(partialPath));
        Assert.Contains(
            "@model SignedInTrustStatusPanelViewModel",
            File.ReadAllText(partialPath),
            StringComparison.Ordinal);
    }

    [Fact]
    public void SignedInTrustPanelPartialIsReusedAcrossHostedViews()
    {
        string[] viewPaths =
        [
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Landing.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Faq.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "ProductStory.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Horizons.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Shelf.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "FeatureDetail.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Now.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "ReleaseUpload.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "SupportSubmitted.cshtml")
        ];

        foreach (string viewPath in viewPaths)
        {
            Assert.True(File.Exists(viewPath));
            Assert.Contains(
                "_SignedInTrustStatusPanel.cshtml",
                File.ReadAllText(viewPath),
                StringComparison.Ordinal);
        }
    }
}
