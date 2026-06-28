using Xunit;

namespace Chummer.Tests;

public sealed class PublicProgressCopyTests
{
    [Fact]
    public void ProgressControllerUsesCurrentReleaseLanguageForCustomerFacingReferences()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicProgressController.cs"));

        Assert.Contains("Customer-facing current state lives on Current release.", controller, StringComparison.Ordinal);
        Assert.Contains("Current customer state lives on <a href=\"/now\">Current release</a>.", controller, StringComparison.Ordinal);
        Assert.Contains(">Open current release<", controller, StringComparison.Ordinal);

        Assert.DoesNotContain("What works today", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("Open What works today", controller, StringComparison.Ordinal);
    }
}
