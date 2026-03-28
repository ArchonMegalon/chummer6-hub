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
    public void PublicLandingViewsIncludeSignedInTrustPanelPartial()
    {
        string[] viewPaths =
        [
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Now.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml")
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
