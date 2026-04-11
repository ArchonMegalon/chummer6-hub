using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingMacDispatchViewTests
{
    [Fact]
    public void MacSignedInDispatchUsesCompactInfoBubbleLayout()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml");

        string controller = File.ReadAllText(controllerPath);
        string view = File.ReadAllText(viewPath);

        Assert.Contains("\"macos\" => \"Install command\"", controller, StringComparison.Ordinal);
        Assert.Contains("\"macos\" => \"Copy this into Terminal.\"", controller, StringComparison.Ordinal);
        Assert.Contains("\"macos\" => \"Copy the install command\"", controller, StringComparison.Ordinal);
        Assert.Contains("\"macos\" => \"Install your personalized Chummer6 app\"", controller, StringComparison.Ordinal);
        Assert.Contains("\"Copy the install command and run it in Terminal.\"", controller, StringComparison.Ordinal);
        Assert.Contains("CompactDispatchLayout: bootstrapScriptDownload && string.Equals(bootstrapPlatform, \"macos\", StringComparison.Ordinal)", controller, StringComparison.Ordinal);

        Assert.Contains("dispatch-compact-lead", view, StringComparison.Ordinal);
        Assert.Contains("dispatch-inline-info", view, StringComparison.Ordinal);
        Assert.Contains("data-install-info", view, StringComparison.Ordinal);
        Assert.Contains("Install details", view, StringComparison.Ordinal);
    }
}
