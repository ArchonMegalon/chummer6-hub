using System;
using System.IO;
using Xunit;

namespace Chummer.Tests;

public sealed class ReleaseUploadEntryPointTests
{
    [Fact]
    public void ReleaseUploadSurfaceIsScopedToTheConfiguredOwner()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));
        string chromeService = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Services", "HubPageChromeService.cs"));
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));

        Assert.Contains("ReleaseUploadAccessPolicy.CanAccess(subject.Email)", controller, StringComparison.Ordinal);
        Assert.Contains("return NotFound();", controller, StringComparison.Ordinal);
        Assert.Contains("ReleaseUploadAccessPolicy.CanAccess(signedInEmail)", chromeService, StringComparison.Ordinal);
        Assert.DoesNotContain("chrome.Authenticated && !hasBuildAction", layout, StringComparison.Ordinal);
    }
}
