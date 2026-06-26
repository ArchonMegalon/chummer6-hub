using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingWindowsDispatchViewTests
{
    [Fact]
    public void WindowsSignedInDispatchUsesSetupExeInsteadOfGuidedPowerShellRoute()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string releaseSelectionPath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "ReleaseSelectionService.cs");
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml");
        string downloadsViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml");

        string controller = File.ReadAllText(controllerPath);
        string releaseSelection = File.ReadAllText(releaseSelectionPath);
        string view = File.ReadAllText(viewPath);
        string downloadsView = File.ReadAllText(downloadsViewPath);

        Assert.Contains("PromoteSecondaryDownload: false", controller, StringComparison.Ordinal);
        Assert.Contains("SecondaryDownloadHref: bootstrapScriptDownload ? rawDownloadHref : null", controller, StringComparison.Ordinal);
        Assert.Contains("SecondaryDownloadLabel: bootstrapScriptDownload ? BuildBootstrapSecondaryDownloadLabel(bootstrapPlatform) : null", controller, StringComparison.Ordinal);
        Assert.Contains("CopyCommandLabel: BuildCopyCommandLabel(bootstrapPlatform)", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("/downloads/install/{artifactId}/bootstrap.ps1", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("DownloadDispatchWindowsBootstrapScript", controller, StringComparison.Ordinal);
        Assert.Contains("Open the Windows setup path, download the published setup .exe", releaseSelection, StringComparison.Ordinal);
        Assert.DoesNotContain("short-lived PowerShell command", releaseSelection, StringComparison.Ordinal);
        Assert.Contains("_ => \"Copy install command\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("Windows preview build", controller, StringComparison.Ordinal);
        Assert.Contains("Supplemental Windows installer", controller, StringComparison.Ordinal);
        Assert.Contains("Download installer", controller, StringComparison.Ordinal);
        Assert.Contains("Direct file mirror", controller, StringComparison.Ordinal);
        Assert.Contains("Use this page when you need this exact installer.", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("Use this route only when support points to this installer.", controller, StringComparison.Ordinal);

        Assert.DoesNotContain("<summary>Guided Windows setup assistant</summary>", view, StringComparison.Ordinal);
        Assert.DoesNotContain("The guided setup assistant below remains the linked-install default.", view, StringComparison.Ordinal);
        Assert.Contains("@PublicDispatchText(Model.CopyCommandLabel)", view, StringComparison.Ordinal);
        Assert.Contains("href=\"@Model.SecondaryDownloadHref\" id=\"startSignedInDownloadButton\">@PublicDispatchText(Model.SecondaryDownloadLabel)</a>", view, StringComparison.Ordinal);
        Assert.True(CountOccurrences(view, "id=\"startSignedInDownloadButton\"") >= 1);
        Assert.DoesNotContain("Windows preview build", downloadsView, StringComparison.Ordinal);
        Assert.DoesNotContain("preview rollout", downloadsView, StringComparison.Ordinal);
        Assert.DoesNotContain("Create account to get preview", downloadsView, StringComparison.Ordinal);
        Assert.Contains("Recommended from your browser. Other platforms stay out of the way.", downloadsView, StringComparison.Ordinal);
        Assert.Contains("<span>Stable</span>", downloadsView, StringComparison.Ordinal);
        Assert.Contains("data-release-lane=\"stable\"", downloadsView, StringComparison.Ordinal);
        Assert.Contains("data-release-lane=\"nightly\"", downloadsView, StringComparison.Ordinal);
        Assert.Contains("Recommended for this browser.", downloadsView, StringComparison.Ordinal);
        Assert.Contains("Newer than Stable.", downloadsView, StringComparison.Ordinal);
        Assert.Contains("<summary>Other downloads</summary>", downloadsView, StringComparison.Ordinal);
        Assert.Contains("No sudo. Updates default to notify.", downloadsView, StringComparison.Ordinal);
        Assert.DoesNotContain("Current public installer", downloadsView, StringComparison.Ordinal);
        Assert.DoesNotContain("Current build", downloadsView, StringComparison.Ordinal);
        Assert.DoesNotContain("Newest build", downloadsView, StringComparison.Ordinal);
        Assert.DoesNotContain("<h2>Help</h2>", downloadsView, StringComparison.Ordinal);
        Assert.DoesNotContain("Use Help for install or update trouble.", downloadsView, StringComparison.Ordinal);
        Assert.DoesNotContain("Need help?", downloadsView, StringComparison.Ordinal);
        Assert.DoesNotContain("Release notes", downloadsView, StringComparison.Ordinal);
        Assert.DoesNotContain("Known issues", downloadsView, StringComparison.Ordinal);
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
