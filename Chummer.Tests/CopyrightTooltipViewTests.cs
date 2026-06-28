using Xunit;

namespace Chummer.Tests;

public sealed class CopyrightTooltipViewTests
{
    [Fact]
    public void OriginDossierViewPublishesCopyrightTooltip()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot(
            "Chummer.Run.Api",
            "Views",
            "Accounts",
            "OriginDossier.cshtml"));

        Assert.Contains("Your strongest copyright claim is in the parts you chose, wrote, edited, and approved.", view, StringComparison.Ordinal);
        Assert.Contains("class=\"inline-help-dot\"", view, StringComparison.Ordinal);
    }

    [Fact]
    public void RunbookViewPublishesCopyrightTooltip()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot(
            "Chummer.Run.Api",
            "Views",
            "PublicLanding",
            "MediaArtifactHorizon.cshtml"));

        Assert.Contains("Runbook rights are strongest in your human curation, editing, commentary, and arrangement.", view, StringComparison.Ordinal);
        Assert.Contains("CopyrightTooltipForHeading", view, StringComparison.Ordinal);
    }
}
