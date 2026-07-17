using Xunit;

namespace Chummer.Tests;

public sealed class BlazorShellComponentTests
{
    [Fact]
    public void SignedInTrustPanelPartialExists()
    {
        string partialPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_SignedInTrustStatusPanel.cshtml");
        string partial = File.ReadAllText(partialPath);

        Assert.True(File.Exists(partialPath));
        Assert.Contains(
            "@model SignedInTrustStatusPanelViewModel",
            partial,
            StringComparison.Ordinal);
        Assert.Contains(
            "@PublicSignedInTrustText(row.Value)",
            partial,
            StringComparison.Ordinal);
    }

    [Fact]
    public void SignedInTrustPanelPartialStaysOnContextHeavyHostedViews()
    {
        string[] viewPaths =
        [
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "ReleaseUpload.cshtml"),
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
