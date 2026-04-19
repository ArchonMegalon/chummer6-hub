using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingWindowsDispatchViewTests
{
    [Fact]
    public void WindowsSignedInDispatchKeepsGuidedInstallerAsDefaultRoute()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml");

        string controller = File.ReadAllText(controllerPath);
        string view = File.ReadAllText(viewPath);

        Assert.Contains("PromoteSecondaryDownload: false", controller, StringComparison.Ordinal);
        Assert.Contains("SecondaryDownloadHref: bootstrapScriptDownload ? rawDownloadHref : null", controller, StringComparison.Ordinal);
        Assert.Contains("SecondaryDownloadLabel: bootstrapScriptDownload ? BuildBootstrapSecondaryDownloadLabel(bootstrapPlatform) : null", controller, StringComparison.Ordinal);
        Assert.Contains("CopyCommandLabel: BuildCopyCommandLabel(bootstrapPlatform)", controller, StringComparison.Ordinal);
        Assert.Contains("\"windows\" => \"Download raw installer fallback\"", controller, StringComparison.Ordinal);
        Assert.Contains("\"windows\" => \"Windows install command\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("\"windows\" => \"Windows install command (advanced)\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("Download the Windows installer .exe below", controller, StringComparison.Ordinal);
        Assert.Contains("_ => \"Copy install command\"", controller, StringComparison.Ordinal);

        Assert.Contains("<summary>Guided Windows setup assistant</summary>", view, StringComparison.Ordinal);
        Assert.Contains("The guided setup assistant below remains the linked-install default.", view, StringComparison.Ordinal);
        Assert.Contains("@Model.CopyCommandLabel", view, StringComparison.Ordinal);
        Assert.Contains("href=\"@Model.SecondaryDownloadHref\" id=\"startSignedInDownloadButton\">@Model.SecondaryDownloadLabel</a>", view, StringComparison.Ordinal);
        Assert.True(CountOccurrences(view, "id=\"startSignedInDownloadButton\"") >= 1);
    }

    private static int CountOccurrences(string text, string needle)
    {
        int count = 0;
        int index = 0;
        while ((index = text.IndexOf(needle, index, StringComparison.Ordinal)) >= 0)
        {
            count++;
            index += needle.Length;
        }

        return count;
    }
}
